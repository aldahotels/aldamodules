import re
from collections import defaultdict
from datetime import timedelta
from email.utils import parseaddr

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext
from odoo.tools.mail import plaintext2html
from odoo.tools.sql import escape_psql

from odoo.addons.pms_ai_tool.tools import guarded_tool, truncate

from ..privacy import mask_email, mask_phone, mask_text

REF_INPUT = {
    "type": "string",
    "maxLength": 20,
    "description": "Number of the ticket as users see it (ticket_ref), not the "
    "internal id. A leading # is accepted.",
}

DEFAULT_LIMIT = 20
MAX_WORDS = 6
DESCRIPTION_CHARS = 1000
MESSAGE_CHARS = 500
MESSAGES_SHOWN = 10
BUCKETS = ("under_2_days", "from_2_to_7_days", "over_7_days")
COUNTERS = ("open",) + BUCKETS + ("unassigned",)

TEAM_INPUT = {
    "type": "integer",
    "minimum": 1,
    "description": "Helpdesk team (id).",
}
PROPERTY_INPUT = {
    "type": "integer",
    "minimum": 1,
    "description": "Hotel (property id).",
}

NOTE_CHARS = 2000
SUMMARY_CHARS = 200
ACTIVITY_NOTE_CHARS = 1000
MAX_DEADLINE_DAYS = 365
TODO_ACTIVITY = "mail.mail_activity_data_todo"


class PmsAiTools(models.AbstractModel):
    """Helpdesk tools of Alda: the helpers first, then the tools one by one."""

    _inherit = "pms.ai.tools"

    # Helpers

    @api.model
    def _alda_helpdesk_local(self, value):
        """Datetime stored in UTC as ISO text in the time zone of the user."""
        if not value:
            return None
        zone = pytz.timezone(self._ai_timezone())
        return pytz.utc.localize(value).astimezone(zone).isoformat(timespec="minutes")

    @api.model
    def _alda_helpdesk_labels(self, model_name, field_name):
        """Labels of a selection field by value, in the language of the user."""
        field = self.env[model_name]._fields[field_name]
        return dict(field._description_selection(self.env))

    @api.model
    def _alda_helpdesk_text(self, html, limit):
        """Plain text of an HTML field: masked, in one line and cut."""
        html = str(html or "")
        try:
            text = html2plaintext(html)
        except Exception:  # noqa: B902 - lxml raises several errors on odd HTML
            text = re.sub(r"<[^>]+>", " ", html)
        return truncate(mask_text(text), limit)

    @api.model
    def _alda_helpdesk_clean(self, text, empty_message):
        """A required free text: stripped, and an error if it is empty."""
        text = (text or "").strip()
        if not text:
            raise UserError(empty_message)
        return text

    @api.model
    def _alda_helpdesk_ref_candidates(self, ticket_ref):
        """The values ``ticket_ref`` may have: the sequence pads to two digits."""
        ref = (ticket_ref or "").strip().lstrip("#").strip()
        if not ref:
            raise UserError(_("Give the number of the ticket (ticket_ref)."))
        return list(dict.fromkeys([ref, ref.zfill(2)]))

    @api.model
    def _alda_helpdesk_scope_domain(self):
        """Tickets of the hotels of the user, and the ones without hotel."""
        return [("pms_property_id", "in", self._ai_scope_property_ids() + [False])]

    @api.model
    def _alda_helpdesk_team_domain(self, team_id):
        team = self.env["helpdesk.team"].search([("id", "=", team_id)])
        if not team:
            raise UserError(_("Unknown team %s, or you cannot see it.") % team_id)
        return [("team_id", "=", team.id)]

    @api.model
    def _alda_helpdesk_find_ticket(self, ticket_ref, write=False):
        """The ticket the user can see (and change, with ``write``) by number."""
        tickets = self.env["helpdesk.ticket"].search(
            self._alda_helpdesk_scope_domain()
            + [("ticket_ref", "in", self._alda_helpdesk_ref_candidates(ticket_ref))],
            limit=2,
        )
        if not tickets:
            raise UserError(
                _("No ticket found with the number %s among those you can see.")
                % (ticket_ref or "").strip()
            )
        if len(tickets) > 1:
            raise UserError(
                _("Several tickets have the number %(ref)s (teams: %(teams)s).")
                % {
                    "ref": tickets[0].ticket_ref,
                    "teams": ", ".join(tickets.mapped("team_id.name")),
                }
            )
        if write:
            tickets.check_access_rights("write")
            tickets.check_access_rule("write")
        return tickets

    @api.model
    def _alda_helpdesk_names(self, ticket):
        """Names of what a ticket points to, read as the web client does.

        A ticket can be visible to someone who follows it although its team is
        private to others, so the names are not subject to the rules of the
        team itself.
        """
        linked = ticket.sudo()
        return {
            "team": linked.team_id.name or None,
            "stage": linked.stage_id.name or None,
            "closed": bool(linked.stage_id.fold),
            "assignee": linked.user_id.name or None,
            "property": linked.pms_property_id.name or None,
        }

    @api.model
    def _alda_helpdesk_ticket_info(self, ticket):
        """The ticket as the previews of the write tools show it."""
        return dict(
            {"ticket_ref": ticket.ticket_ref, "title": ticket.name},
            **self._alda_helpdesk_names(ticket),
        )

    # Tool: alda_helpdesk_ticket_search

    @api.model
    def _alda_helpdesk_search_row(self, ticket):
        return dict(
            self._alda_helpdesk_ticket_info(ticket),
            created=self._alda_helpdesk_local(ticket.create_date),
            last_update=self._alda_helpdesk_local(ticket.write_date),
        )

    @guarded_tool(
        input_schema={
            "text": {
                "type": "string",
                "maxLength": 100,
                "description": "Words to look for in the title or the description "
                f"(at most {MAX_WORDS}), all of them must appear.",
            },
            "ticket_ref": REF_INPUT,
            "property_id": PROPERTY_INPUT,
            "team_id": TEAM_INPUT,
            "stage_kind": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "Open tickets (default), closed ones or all. A "
                "ticket is closed when its stage is folded.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": f"Tickets returned ({DEFAULT_LIMIT}).",
            },
        },
        output_schema={
            "total": {"type": "integer"},
            "tickets": {"type": "array", "items": {"type": "object"}},
        },
    )
    def _ai_alda_helpdesk_ticket_search(
        self,
        text=None,
        ticket_ref=None,
        property_id=None,
        team_id=None,
        stage_kind="open",
        limit=DEFAULT_LIMIT,
    ):
        domain = self._alda_helpdesk_scope_domain()
        if property_id:
            self._ai_scope_property_ids([property_id])
            domain.append(("pms_property_id", "=", property_id))
        if team_id:
            domain += self._alda_helpdesk_team_domain(team_id)
        if stage_kind != "all":
            domain.append(("stage_id.fold", "=", stage_kind == "closed"))
        if ticket_ref:
            domain.append(
                ("ticket_ref", "in", self._alda_helpdesk_ref_candidates(ticket_ref))
            )
        for word in (text or "").split()[:MAX_WORDS]:
            pattern = escape_psql(word)
            domain += [
                "|",
                ("name", "ilike", pattern),
                ("description", "ilike", pattern),
            ]
        tickets = self.env["helpdesk.ticket"]
        total = tickets.search_count(domain)
        shown = tickets.search(
            domain, order="write_date desc, id desc", limit=self._ai_max_rows(limit)
        )
        warnings = []
        if total > len(shown):
            warnings.append(
                _(
                    "Only the first %(shown)s of %(total)s tickets are shown: "
                    "narrow the search."
                )
                % {"shown": len(shown), "total": total}
            )
        return {
            "summary": _("%(shown)s of the %(total)s tickets that match.")
            % {"shown": len(shown), "total": total},
            "definitions": [
                _(
                    "The number users see is ticket_ref, not the internal id. A "
                    "ticket is open while its stage is not folded in the "
                    "pipeline of its team."
                ),
                _(
                    "Tickets without a hotel are included (every helpdesk user "
                    "sees them); the rest are limited to your hotels."
                ),
                _(
                    "last_update is the last time the ticket was saved. Times "
                    "are in the time zone %s."
                )
                % self._ai_timezone(),
            ],
            "warnings": warnings,
            "result": {
                "total": total,
                "tickets": [self._alda_helpdesk_search_row(t) for t in shown],
            },
        }

    # Tool: alda_helpdesk_ticket_detail

    @api.model
    def _alda_helpdesk_author(self, message):
        if message.author_id:
            return message.author_id.name
        name, email = parseaddr(message.email_from or "")
        return name or mask_email(email) or None

    @api.model
    def _alda_helpdesk_messages(self, ticket):
        """The last comments and e-mails of the ticket, oldest first."""
        domain = [
            ("model", "=", "helpdesk.ticket"),
            ("res_id", "=", ticket.id),
            ("message_type", "in", ("comment", "email")),
        ]
        messages = self.env["mail.message"]
        last = messages.search(domain, order="id desc", limit=MESSAGES_SHOWN)
        rows = [
            {
                "author": self._alda_helpdesk_author(message),
                "date": self._alda_helpdesk_local(message.date),
                "internal": bool(message.is_internal or message.subtype_id.internal),
                "body": self._alda_helpdesk_text(message.body, MESSAGE_CHARS),
            }
            for message in last.sorted("id")
        ]
        return rows, messages.search_count(domain)

    @api.model
    def _alda_helpdesk_sla(self, ticket):
        return {
            "uses_sla": bool(ticket.use_sla),
            "deadline": self._alda_helpdesk_local(ticket.sla_deadline),
            "failed": bool(ticket.sla_fail),
            "policies": [
                {
                    "policy": status.sla_id.name,
                    "status": status.status,
                    "deadline": self._alda_helpdesk_local(status.deadline),
                    "reached": self._alda_helpdesk_local(status.reached_datetime),
                }
                for status in ticket.sla_status_ids
            ],
        }

    @guarded_tool(
        input_schema={"ticket_ref": REF_INPUT},
        output_schema={
            "ticket": {"type": "object"},
            "customer": {"type": "object"},
            "links": {"type": "object"},
            "sla": {"type": "object"},
            "message_count": {"type": "integer"},
            "messages": {"type": "array", "items": {"type": "object"}},
        },
        required_inputs=["ticket_ref"],
        log_result=False,
    )
    def _ai_alda_helpdesk_ticket_detail(self, ticket_ref):
        ticket = self._alda_helpdesk_find_ticket(ticket_ref)
        messages, message_count = self._alda_helpdesk_messages(ticket)
        priorities = self._alda_helpdesk_labels("helpdesk.ticket", "priority")
        info = dict(
            self._alda_helpdesk_ticket_info(ticket),
            description=self._alda_helpdesk_text(ticket.description, DESCRIPTION_CHARS),
            priority=priorities.get(ticket.priority, ticket.priority),
            type=ticket.ticket_type_id.name or None,
            tags=ticket.tag_ids.mapped("name"),
            created=self._alda_helpdesk_local(ticket.create_date),
            last_update=self._alda_helpdesk_local(ticket.write_date),
            assigned=self._alda_helpdesk_local(ticket.assign_date),
            closed_on=self._alda_helpdesk_local(ticket.close_date),
        )
        return {
            "summary": _("Ticket %(ref)s, %(stage)s: %(title)s.")
            % {
                "ref": ticket.ticket_ref,
                "stage": ticket.sudo().stage_id.name or "-",
                "title": ticket.name,
            },
            "definitions": [
                _(
                    "The customer is the person who opened the ticket; the "
                    "e-mail and the phone are masked, and so are the e-mails "
                    "and phone numbers found in the texts."
                ),
                _(
                    "The links stored on a ticket are the hotel and the room "
                    "(Alda tickets have no folio field)."
                ),
                _(
                    "Messages: the last %(count)s comments and e-mails, oldest "
                    "first, as plain text cut to %(chars)s characters. Internal "
                    "ones are notes that the customer does not see."
                )
                % {"count": MESSAGES_SHOWN, "chars": MESSAGE_CHARS},
                _("Times are in the time zone %s.") % self._ai_timezone(),
            ],
            "warnings": [],
            "result": {
                "ticket": info,
                "customer": {
                    "name": ticket.partner_name or ticket.partner_id.name or None,
                    "email": mask_email(ticket.partner_email),
                    "phone": mask_phone(ticket.partner_phone),
                },
                "links": {
                    "property": {
                        "id": ticket.pms_property_id.id,
                        "name": ticket.pms_property_id.name,
                    }
                    if ticket.pms_property_id
                    else None,
                    "room": ticket.pms_room_id.name or None,
                },
                "sla": self._alda_helpdesk_sla(ticket),
                "message_count": message_count,
                "messages": messages,
            },
        }

    # Tool: alda_helpdesk_backlog

    @api.model
    def _alda_helpdesk_backlog_counts(self, domain):
        """Open tickets by team, stage and hotel: count, age and unassigned."""
        now = fields.Datetime.now()
        two_days, seven_days = now - timedelta(days=2), now - timedelta(days=7)
        filters = {
            "under_2_days": [("create_date", ">", two_days)],
            "from_2_to_7_days": [
                ("create_date", "<=", two_days),
                ("create_date", ">=", seven_days),
            ],
            "over_7_days": [("create_date", "<", seven_days)],
            "unassigned": [("user_id", "=", False)],
        }
        names = {}
        cells = defaultdict(lambda: dict.fromkeys(COUNTERS, 0))
        tickets = self.env["helpdesk.ticket"]
        for counter, extra in filters.items():
            groups = tickets.read_group(
                domain + extra,
                ["team_id"],
                ["team_id", "stage_id", "pms_property_id"],
                lazy=False,
            )
            for group in groups:
                key = []
                for field in ("team_id", "stage_id", "pms_property_id"):
                    value = group[field]
                    key.append(value[0] if value else False)
                    names[(field, key[-1])] = value[1] if value else None
                cells[tuple(key)][counter] += group["__count"]
                if counter in BUCKETS:
                    cells[tuple(key)]["open"] += group["__count"]
        return cells, names

    @guarded_tool(
        input_schema={"team_id": TEAM_INPUT, "property_id": PROPERTY_INPUT},
        output_schema={
            "totals": {"type": "object"},
            "by_team": {"type": "array", "items": {"type": "object"}},
            "rows": {"type": "array", "items": {"type": "object"}},
        },
    )
    def _ai_alda_helpdesk_backlog(self, team_id=None, property_id=None):
        domain = self._alda_helpdesk_scope_domain() + [("stage_id.fold", "=", False)]
        if property_id:
            self._ai_scope_property_ids([property_id])
            domain.append(("pms_property_id", "=", property_id))
        if team_id:
            domain += self._alda_helpdesk_team_domain(team_id)
        cells, names = self._alda_helpdesk_backlog_counts(domain)
        totals = dict.fromkeys(COUNTERS, 0)
        by_team = defaultdict(lambda: dict.fromkeys(COUNTERS, 0))
        rows = []
        for (team, stage, prop), counters in cells.items():
            for counter in COUNTERS:
                totals[counter] += counters[counter]
                by_team[team][counter] += counters[counter]
            rows.append(
                dict(
                    {
                        "team": names[("team_id", team)],
                        "stage": names[("stage_id", stage)],
                        "property_id": prop or None,
                        "property": names[("pms_property_id", prop)],
                    },
                    **counters,
                )
            )
        rows.sort(key=lambda r: (-r["open"], r["team"] or "", r["stage"] or ""))
        team_rows = sorted(
            (
                dict(
                    {"team_id": team or None, "team": names[("team_id", team)]},
                    **counters,
                )
                for team, counters in by_team.items()
            ),
            key=lambda r: (-r["open"], r["team"] or ""),
        )
        warnings = []
        return {
            "summary": _(
                "%(open)s open tickets: %(new)s under 2 days, %(mid)s from 2 to "
                "7 days, %(old)s over 7 days; %(unassigned)s without assignee."
            )
            % {
                "open": totals["open"],
                "new": totals["under_2_days"],
                "mid": totals["from_2_to_7_days"],
                "old": totals["over_7_days"],
                "unassigned": totals["unassigned"],
            },
            "definitions": [
                _(
                    "Open: tickets whose stage is not folded in the pipeline "
                    "of their team. Tickets without a hotel are included; the "
                    "rest are limited to your hotels."
                ),
                _(
                    "Age counts from the creation of the ticket: under 2 days, "
                    "from 2 to 7 days and over 7 days add up to the open "
                    "tickets. unassigned counts the open tickets without "
                    "assignee, whatever their age."
                ),
            ],
            "warnings": warnings,
            "result": {
                "totals": totals,
                "by_team": team_rows,
                "rows": self._ai_limit_rows(rows, warnings),
            },
        }

    # Tool: alda_helpdesk_ticket_add_note

    @guarded_tool(
        input_schema={
            "ticket_ref": REF_INPUT,
            "note": {
                "type": "string",
                "maxLength": NOTE_CHARS,
                "description": "Text of the internal note, in plain text.",
            },
        },
        output_schema={
            "ticket": {"type": "object"},
            "note": {"type": "string"},
            "visibility": {"type": "string"},
        },
        required_inputs=["ticket_ref", "note"],
        write=True,
        apply="_alda_helpdesk_ticket_add_note_apply",
    )
    def _ai_alda_helpdesk_ticket_add_note(self, ticket_ref, note):
        note = self._alda_helpdesk_clean(note, _("The note is empty."))
        ticket = self._alda_helpdesk_find_ticket(ticket_ref, write=True)
        return {
            "summary": _("Post an internal note on the ticket %(ref)s: %(title)s.")
            % {"ref": ticket.ticket_ref, "title": ticket.name},
            "definitions": [
                _(
                    "The note is internal: the customer does not see it and "
                    "nobody is named in it, so no e-mail goes to anyone in "
                    "particular. It is posted in the name of the user who "
                    "confirms it."
                ),
            ],
            "warnings": [],
            "result": {
                "ticket": self._alda_helpdesk_ticket_info(ticket),
                "note": note,
                "visibility": _("Internal note"),
            },
            "plan": {"ticket_id": ticket.id, "note": note},
        }

    def _alda_helpdesk_ticket_add_note_apply(self, plan, ticket_ref, note):
        ticket = self.env["helpdesk.ticket"].browse(plan["ticket_id"]).exists()
        if not ticket:
            raise UserError(_("The ticket no longer exists."))
        ticket.check_access_rights("write")
        ticket.check_access_rule("write")
        message = ticket.message_post(
            body=plaintext2html(plan["note"]),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
            partner_ids=[],
        )
        return {
            "summary": _("Internal note posted on the ticket %s.") % ticket.ticket_ref,
            "result": {"message_id": message.id, "ticket_ref": ticket.ticket_ref},
        }

    # Tool: alda_helpdesk_activity_schedule

    @api.model
    def _alda_helpdesk_assignee(self, user_id, ticket):
        """An internal, active user who can read the ticket."""
        user = self.env["res.users"].search(
            [("id", "=", user_id), ("share", "=", False)]
        )
        if not user:
            raise UserError(
                _("User %s is not an active internal user that you can see.") % user_id
            )
        as_user = ticket.with_user(user).with_context(
            allowed_company_ids=user.company_ids.ids
        )
        try:
            as_user.check_access_rights("read")
            as_user.check_access_rule("read")
        except AccessError:
            raise UserError(
                _(
                    "%(user)s cannot read the ticket %(ref)s, so the activity "
                    "would not reach them. Choose someone of the team."
                )
                % {"user": user.name, "ref": ticket.ticket_ref}
            ) from None
        return user

    @api.model
    def _alda_helpdesk_check_deadline(self, date_deadline):
        today = fields.Date.context_today(self)
        if date_deadline < today:
            raise UserError(_("The deadline cannot be in the past."))
        if date_deadline > today + timedelta(days=MAX_DEADLINE_DAYS):
            raise UserError(
                _("The deadline cannot be more than %s days away.") % MAX_DEADLINE_DAYS
            )

    @guarded_tool(
        input_schema={
            "ticket_ref": REF_INPUT,
            "user_id": {
                "type": "integer",
                "minimum": 1,
                "description": "User who gets the activity (id): an internal "
                "user who can read the ticket.",
            },
            "date_deadline": {
                "type": "string",
                "format": "date",
                "description": "Deadline (YYYY-MM-DD): today or later, at most "
                f"{MAX_DEADLINE_DAYS} days away.",
            },
            "summary": {
                "type": "string",
                "maxLength": SUMMARY_CHARS,
                "description": "Title of the activity.",
            },
            "note": {
                "type": "string",
                "maxLength": ACTIVITY_NOTE_CHARS,
                "description": "Details of the activity, in plain text (optional).",
            },
        },
        output_schema={
            "ticket": {"type": "object"},
            "assignee": {"type": "object"},
            "deadline": {"type": "string"},
            "summary": {"type": "string"},
            "note": {"type": "string"},
            "activity_type": {"type": "string"},
        },
        required_inputs=["ticket_ref", "user_id", "date_deadline", "summary"],
        write=True,
        apply="_alda_helpdesk_activity_schedule_apply",
    )
    def _ai_alda_helpdesk_activity_schedule(
        self, ticket_ref, user_id, date_deadline, summary, note=None
    ):
        summary = self._alda_helpdesk_clean(summary, _("The summary is empty."))
        note = (note or "").strip()
        self._alda_helpdesk_check_deadline(date_deadline)
        ticket = self._alda_helpdesk_find_ticket(ticket_ref, write=True)
        user = self._alda_helpdesk_assignee(user_id, ticket)
        open_activity = (
            self.env["mail.activity"]
            .sudo()
            .search_count(
                [
                    ("res_model", "=", "helpdesk.ticket"),
                    ("res_id", "=", ticket.id),
                    ("user_id", "=", user.id),
                    ("summary", "=", summary),
                ]
            )
        )
        if open_activity:
            raise UserError(
                _(
                    "%(user)s already has an open activity %(summary)s on the "
                    "ticket %(ref)s."
                )
                % {"user": user.name, "summary": summary, "ref": ticket.ticket_ref}
            )
        return {
            "summary": _(
                "Schedule the activity %(summary)s on the ticket %(ref)s for "
                "%(user)s, due on %(date)s."
            )
            % {
                "summary": summary,
                "ref": ticket.ticket_ref,
                "user": user.name,
                "date": date_deadline,
            },
            "definitions": [
                _(
                    "The activity is a To-Do on the ticket. Odoo sends the "
                    "assigned user its usual assignment email and the user "
                    "becomes a follower of the ticket."
                ),
            ],
            "warnings": [
                _(
                    "%s will receive the assignment email of Odoo when the "
                    "activity is created."
                )
                % user.name
            ],
            "result": {
                "ticket": self._alda_helpdesk_ticket_info(ticket),
                "assignee": {"user_id": user.id, "name": user.name},
                "deadline": date_deadline.isoformat(),
                "summary": summary,
                "note": note or None,
                "activity_type": _("To-Do"),
            },
            "plan": {
                "ticket_id": ticket.id,
                "user_id": user.id,
                "summary": summary,
                "note": note,
            },
        }

    def _alda_helpdesk_activity_schedule_apply(
        self, plan, ticket_ref, user_id, date_deadline, summary, note=None
    ):
        ticket = self.env["helpdesk.ticket"].browse(plan["ticket_id"]).exists()
        if not ticket:
            raise UserError(_("The ticket no longer exists."))
        ticket.check_access_rights("write")
        ticket.check_access_rule("write")
        activity = ticket.activity_schedule(
            TODO_ACTIVITY,
            date_deadline=date_deadline,
            summary=plan["summary"],
            note=plaintext2html(plan["note"]) if plan["note"] else "",
            user_id=plan["user_id"],
        )
        return {
            "summary": _("Activity created on the ticket %(ref)s for %(user)s.")
            % {"ref": ticket.ticket_ref, "user": activity.user_id.name},
            "result": {
                "activity_id": activity.id,
                "ticket_ref": ticket.ticket_ref,
                "assignee": activity.user_id.name,
                "deadline": activity.date_deadline.isoformat(),
            },
        }
