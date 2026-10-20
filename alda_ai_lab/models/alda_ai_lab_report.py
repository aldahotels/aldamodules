import re

import pytz
from markupsafe import Markup

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import get_lang

from odoo.addons.pms_ai_tool.tools import guarded_tool, truncate

from .alda_ai_lab_schedule import FREQUENCIES, PERIODS, WEEKDAYS, period_dates
from .lab import lab_silence

MAX_RECIPIENTS = 10
TABLE_ROWS = 10
TABLE_COLUMNS = 8
TABLE_SECTIONS = 4
TIME_PATTERN = r"([01]\d|2[0-3]):[0-5]\d"

SCHEDULE_INPUT = {
    "tool_name": {
        "type": "string",
        "maxLength": 64,
        "description": "Name of the catalogue READ tool to run, for example "
        "pms_discounts_summary, pms_service_nights, pms_salesperson_sales, "
        "pms_salesperson_top_customers, pms_salesperson_portfolio or "
        "pms_salesperson_cooling_customers.",
    },
    "period": {
        "type": "string",
        "enum": list(PERIODS),
        "description": "Period the report covers, computed on the day of each "
        "run: " + "; ".join(f"{key} = {label}" for key, label in PERIODS.items()),
    },
    "frequency": {"type": "string", "enum": list(FREQUENCIES)},
    "weekday": {
        "type": "string",
        "enum": WEEKDAYS,
        "description": "Day of the week, for weekly reports.",
    },
    "day_of_month": {
        "type": "integer",
        "minimum": 1,
        "maximum": 31,
        "description": "Day of the month, for monthly reports (31 = last day).",
    },
    "time": {
        "type": "string",
        "maxLength": 5,
        "pattern": TIME_PATTERN,
        "description": "Local time of the run, HH:MM (for example 08:00).",
    },
    "property_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "maxItems": 200,
        "description": "Properties to include, if the tool takes them. Default: "
        "all the recipient's.",
    },
    "salesperson_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "maxItems": 20,
        "description": "Users of the salespeople, for the salesperson tools.",
    },
    "recipient_user_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "maxItems": MAX_RECIPIENTS,
        "description": "Users who get the report. Default: me. Only administrators "
        "can schedule reports for other people.",
    },
    "send_now": {
        "type": "boolean",
        "description": "Also send the first report right away.",
    },
}


def _label(key):
    return str(key).replace("_", " ").capitalize()


class AldaAiLabReportTools(models.AbstractModel):
    _name = "alda.ai.lab.report.tools"
    _inherit = "alda.ai.lab.mixin"
    _description = "AI lab tools: scheduled reports"

    # Rendering of a catalogue tool response as a chat message

    @api.model
    def _lab_format(self, value, lang):
        if value is None or value == "":
            return "—"
        if isinstance(value, bool):
            return _("yes") if value else _("no")
        if isinstance(value, float):
            return lang.format("%.2f", value, grouping=True)
        if isinstance(value, int):
            return lang.format("%d", value, grouping=True)
        if isinstance(value, list):
            if all(not isinstance(item, dict | list) for item in value):
                return truncate(", ".join(map(str, value)), 60)
            return _("%s items") % len(value)
        if isinstance(value, dict):
            return truncate(
                ", ".join(f"{_label(k)}: {v}" for k, v in value.items()), 60
            )
        return truncate(value, 80)

    @api.model
    def _lab_render_table(self, key, value, lang):
        """A list of dicts as a table, a dict of scalars as key/value rows."""
        if isinstance(value, list) and value and isinstance(value[0], dict):
            columns = [
                column
                for column in value[0]
                if not re.search(r"(^|_)ids?$", column)
                and not isinstance(value[0][column], dict | list)
            ][:TABLE_COLUMNS]
            if not columns:
                return Markup("")
            head = Markup("").join(
                Markup("<th>%s</th>") % _label(column) for column in columns
            )
            rows = Markup("").join(
                Markup("<tr>%s</tr>")
                % Markup("").join(
                    Markup("<td>%s</td>") % self._lab_format(row.get(column), lang)
                    for column in columns
                )
                for row in value[:TABLE_ROWS]
            )
            more = (
                Markup("<p><small>%s</small></p>")
                % (_("… and %s more rows.") % (len(value) - TABLE_ROWS))
                if len(value) > TABLE_ROWS
                else Markup("")
            )
            return Markup(
                '<p><b>%s</b></p><table class="table table-sm table-bordered">'
                "<thead><tr>%s</tr></thead><tbody>%s</tbody></table>%s"
            ) % (_label(key), head, rows, more)
        if isinstance(value, dict) and value:
            rows = Markup("").join(
                Markup("<tr><td>%s</td><td>%s</td></tr>")
                % (_label(name), self._lab_format(item, lang))
                for name, item in list(value.items())[: TABLE_ROWS + 2]
                if not isinstance(item, dict | list)
            )
            if not rows:
                return Markup("")
            return Markup(
                '<p><b>%s</b></p><table class="table table-sm table-bordered">'
                "<tbody>%s</tbody></table>"
            ) % (_label(key), rows)
        return Markup("")

    @api.model
    def _lab_render_report(self, schedule, response, user):
        # get_lang falls back to an active language; _lang_get would not.
        lang = get_lang(self.env, user.lang)
        period = response.get("period") or {}
        heading = schedule.name
        if period.get("date_from") or period.get("date_to"):
            heading = "%s (%s → %s)" % (
                heading,
                period.get("date_from", "…"),
                period.get("date_to", "…"),
            )
        parts = [Markup("<p><b>%s</b></p>") % heading]
        if response.get("summary"):
            parts.append(Markup("<p>%s</p>") % response["summary"])
        warnings = response.get("warnings") or []
        if warnings:
            parts.append(
                Markup("<p><b>%s</b></p><ul>%s</ul>")
                % (
                    _("Warnings"),
                    Markup("").join(
                        Markup("<li>%s</li>") % truncate(text, 300)
                        for text in warnings[:5]
                    ),
                )
            )
        tables = [
            table
            for table in (
                self._lab_render_table(key, value, lang)
                for key, value in (response.get("result") or {}).items()
            )
            if table
        ]
        parts.extend(tables[:TABLE_SECTIONS])
        parts.append(Markup("<p><small>%s</small></p>") % self._lab_footer(schedule))
        return Markup("").join(parts)

    @api.model
    def _lab_render_failure(self, schedule, error):
        text = error.args[0] if getattr(error, "args", None) else str(error)
        if not isinstance(error, UserError | AccessError):
            text = _("Internal error; it has been logged.")
        return Markup("<p><b>%s</b></p><p>%s</p><p><small>%s</small></p>") % (
            schedule.name,
            _("The report could not be prepared: %s") % text,
            self._lab_footer(schedule),
        )

    @api.model
    def _lab_footer(self, schedule):
        return _(
            "Scheduled with AI by %(owner)s (%(when)s). To change or cancel it, ask "
            "Claude about the scheduled report %(id)s."
        ) % {
            "owner": schedule.user_id.name,
            "when": schedule._lab_when(),
            "id": schedule.id,
        }

    @api.model
    def _lab_post_to_chat(self, user, body):
        """Post ``body`` in the direct chat between ``user`` and OdooBot."""
        odoobot = self.env.ref("base.partner_root")
        with lab_silence(self.env["mail.channel"].with_user(user)) as channels:
            # channel_get pairs the current user with the given partners.
            info = channels.channel_get([odoobot.id])
            # Posted by OdooBot itself: as the recipient (even with sudo) the
            # message would be stored as already read. No partner_ids, which
            # would email them.
            return (
                channels.browse(info["id"])
                .with_user(SUPERUSER_ID)
                .message_post(
                    body=body,
                    author_id=odoobot.id,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
            )

    # Shared checks

    @api.model
    def _lab_find_tool(self, tool_name):
        tool = self.env["ai.tool"].sudo().search([("name", "=", tool_name)], limit=1)
        if not tool:
            raise UserError(_("There is no tool called %s.") % tool_name)
        return tool

    @api.model
    def _lab_recipients(self, recipient_user_ids, tool):
        users = self.env["res.users"].sudo().browse(recipient_user_ids or [])
        if not users:
            users = self.env.user
        missing = set(recipient_user_ids or []) - set(users.exists().ids)
        if missing:
            raise UserError(
                _("Unknown users: %s.") % ", ".join(map(str, sorted(missing)))
            )
        if users - self.env.user and not self.env.user.has_group("base.group_system"):
            raise AccessError(
                _("Only administrators can schedule reports for other people.")
            )
        refused = users.filtered(lambda user: user.share or not user.active)
        if refused:
            raise UserError(
                _("Reports only go to active internal users, not to: %s.")
                % ", ".join(refused.mapped("name"))
            )
        not_allowed = users.filtered(
            lambda user: not tool.with_user(user)._pms_ai_is_allowed()
        )
        if not_allowed:
            raise UserError(
                _("These users are not allowed to use the tool %(tool)s: %(users)s.")
                % {"tool": tool.name, "users": ", ".join(not_allowed.mapped("name"))}
            )
        return users

    @api.model
    def _lab_schedule_values(
        self,
        tool,
        period,
        frequency,
        time,
        weekday=None,
        day_of_month=None,
        property_ids=None,
        salesperson_ids=None,
        recipients=None,
    ):
        if frequency == "weekly" and not weekday:
            raise UserError(_("A weekly report needs the day of the week."))
        if frequency == "monthly" and not day_of_month:
            raise UserError(_("A monthly report needs the day of the month."))
        hour, minute = (int(part) for part in time.split(":"))
        property_ids = list(property_ids or [])
        if property_ids:
            # The schedule may go to other people, but its owner must see the
            # properties it names.
            self.env["pms.ai.tools"]._ai_scope_property_ids(property_ids)
        self.env["alda.ai.lab.schedule"]._lab_check_schedulable(tool, property_ids)
        return {
            "tool_id": tool.id,
            "period": period,
            "frequency": frequency,
            "weekday": weekday if frequency == "weekly" else False,
            "day_of_month": day_of_month if frequency == "monthly" else 0,
            "time_of_day": hour + minute / 60,
            "tz": self.env.user.tz or "Europe/Madrid",
            "property_ids": [(6, 0, property_ids)],
            "salesperson_ids": [(6, 0, list(salesperson_ids or []))],
            "recipient_ids": [(6, 0, recipients.ids)],
            "user_id": self.env.user.id,
        }

    @api.model
    def _lab_describe(self, schedule):
        return {
            "schedule_id": schedule.id or None,
            "name": schedule.name,
            "tool": schedule.tool_id.name,
            "period": PERIODS.get(schedule.period),
            "when": schedule._lab_when(),
            "timezone": schedule.tz,
            "recipients": (schedule.recipient_ids or schedule.user_id).mapped("name"),
            "properties": schedule.property_ids.mapped("name"),
            "state": schedule.state,
        }

    @api.model
    def _lab_ensure_dispatcher(self):
        # A deploy to staging neutralizes the database and switches every
        # scheduled action off: the lab turns its own back on when used.
        cron = self.env.ref(
            "alda_ai_lab.ir_cron_lab_dispatch", raise_if_not_found=False
        )
        if cron and not cron.sudo().active:
            cron.sudo().active = True

    # Tools

    @guarded_tool(
        input_schema=SCHEDULE_INPUT,
        output_schema={
            "schedule": {"type": "object"},
            "next_runs": {"type": "array", "items": {"type": "string"}},
            "arguments_today": {"type": "object"},
            "sample": {"type": "object"},
            "send_now": {"type": "boolean"},
        },
        required_inputs=["tool_name", "period", "frequency", "time"],
        write=True,
        apply="_ai_lab_report_schedule_apply",
    )
    def _ai_lab_report_schedule(
        self,
        tool_name,
        period,
        frequency,
        time,
        weekday=None,
        day_of_month=None,
        property_ids=None,
        salesperson_ids=None,
        recipient_user_ids=None,
        send_now=False,
    ):
        self._lab_check()
        tool = self._lab_find_tool(tool_name)
        recipients = self._lab_recipients(recipient_user_ids, tool)
        values = self._lab_schedule_values(
            tool,
            period,
            frequency,
            time,
            weekday,
            day_of_month,
            property_ids,
            salesperson_ids,
            recipients,
        )
        draft = self.env["alda.ai.lab.schedule"].new(values)
        # Everything about the draft first: the sample below rolls back its
        # savepoint, which clears the cache where a new record lives.
        arguments = draft._lab_tool_arguments()
        description = self._lab_describe(draft)
        next_runs = draft._lab_next_runs(3)
        date_from, date_to = period_dates(period, draft._lab_local_today())
        sample = tool.with_user(self.env.user)._execute_tool(**arguments)
        spec = {
            "values": {
                key: value
                for key, value in values.items()
                if key not in ("property_ids", "salesperson_ids", "recipient_ids")
            },
            "property_ids": list(property_ids or []),
            "salesperson_ids": list(salesperson_ids or []),
            "recipient_ids": recipients.ids,
            "send_now": bool(send_now),
        }
        return {
            "summary": _(
                "Report %(name)s for %(recipients)s; first run %(first)s. The "
                "sample below is what it would send today."
            )
            % {
                "name": description["name"],
                "recipients": ", ".join(recipients.mapped("name")),
                "first": next_runs[0],
            },
            "period": {"date_from": date_from, "date_to": date_to},
            "definitions": [
                _(
                    "Each run computes the period again on its day, in the "
                    "timezone of the owner, and runs the tool with the permissions "
                    "of each recipient."
                ),
                _(
                    "The report arrives in the recipient's chat with OdooBot. "
                    "Nobody outside Odoo receives it."
                ),
            ],
            "warnings": [
                _(
                    "Lab tool: only for staging. The data of staging is a copy of "
                    "production of a past date."
                )
            ]
            + [str(text) for text in sample.get("warnings") or []][:3],
            "result": {
                "schedule": description,
                "next_runs": next_runs,
                "arguments_today": arguments,
                "sample": {
                    "summary": sample.get("summary"),
                    "result": sample.get("result"),
                },
                "send_now": bool(send_now),
            },
            "binding": spec,
            "plan": spec,
        }

    def _ai_lab_report_schedule_apply(self, plan, **arguments):
        self._lab_check()
        values = dict(
            plan["values"],
            property_ids=[(6, 0, plan["property_ids"])],
            salesperson_ids=[(6, 0, plan["salesperson_ids"])],
            recipient_ids=[(6, 0, plan["recipient_ids"])],
        )
        schedule = self.env["alda.ai.lab.schedule"].sudo().create(values)
        self._lab_ensure_dispatcher()
        schedule._lab_set_next_run(fields.Datetime.now())
        sent = schedule._lab_send() if plan["send_now"] else None
        return {
            "summary": _("Scheduled report %(id)s created: %(name)s.")
            % {"id": schedule.id, "name": schedule.name}
            + (
                _(" The first one has been sent to the chat with OdooBot.")
                if sent
                else _(" The report sent now failed: %s") % schedule.last_error
                if sent is False
                else ""
            ),
            "result": {
                "schedule": self._lab_describe(schedule),
                "next_runs": schedule._lab_next_runs(3),
                "sent_now": bool(sent),
                "url": self._lab_url(schedule),
            },
        }

    @guarded_tool(
        input_schema={
            "include_cancelled": {
                "type": "boolean",
                "description": "Also list cancelled reports.",
            },
        },
        output_schema={"schedules": {"type": "array", "items": {"type": "object"}}},
    )
    def _ai_lab_report_schedules(self, include_cancelled=False):
        self._lab_check()
        domain = [
            "|",
            ("user_id", "=", self.env.uid),
            ("recipient_ids", "in", [self.env.uid]),
        ]
        if not include_cancelled:
            domain.append(("state", "!=", "cancelled"))
        schedules = self.env["alda.ai.lab.schedule"].sudo().search(domain)
        tz = pytz.timezone(self.env.user.tz or "UTC")

        def local(value):
            if not value:
                return None
            return pytz.utc.localize(value).astimezone(tz).strftime("%Y-%m-%d %H:%M")

        rows = [
            dict(
                self._lab_describe(schedule),
                owner=schedule.user_id.name,
                next_run=local(schedule.next_run),
                last_run=local(schedule.last_run),
                last_result=schedule.last_state or None,
                last_error=truncate(schedule.last_error, 200),
                runs=schedule.run_count,
            )
            for schedule in schedules
        ]
        return {
            "summary": _("%s scheduled reports.") % len(rows),
            "result": {"schedules": rows},
        }

    @guarded_tool(
        input_schema={
            "schedule_id": {"type": "integer", "description": "Scheduled report."},
            "action": {
                "type": "string",
                "enum": ["pause", "resume", "cancel", "send_now", "update"],
                "description": "update changes the fields given below.",
            },
            "period": SCHEDULE_INPUT["period"],
            "frequency": SCHEDULE_INPUT["frequency"],
            "weekday": SCHEDULE_INPUT["weekday"],
            "day_of_month": SCHEDULE_INPUT["day_of_month"],
            "time": SCHEDULE_INPUT["time"],
            "recipient_user_ids": SCHEDULE_INPUT["recipient_user_ids"],
        },
        output_schema={"schedule": {"type": "object"}, "changes": {"type": "object"}},
        required_inputs=["schedule_id", "action"],
        write=True,
        apply="_ai_lab_report_schedule_manage_apply",
    )
    def _ai_lab_report_schedule_manage(
        self,
        schedule_id,
        action,
        period=None,
        frequency=None,
        weekday=None,
        day_of_month=None,
        time=None,
        recipient_user_ids=None,
    ):
        self._lab_check()
        schedule = self.env["alda.ai.lab.schedule"].sudo().browse(schedule_id).exists()
        if not schedule:
            raise UserError(_("There is no scheduled report %s.") % schedule_id)
        if schedule.user_id != self.env.user and not self.env.user.has_group(
            "base.group_system"
        ):
            raise AccessError(
                _("Only the owner can change the report %s.") % schedule_id
            )
        if schedule.state == "cancelled" and action != "resume":
            raise UserError(_("The report %s is cancelled.") % schedule_id)
        changes = {}
        if action == "pause":
            changes = {"state": "paused"}
        elif action in ("resume", "cancel"):
            changes = {"state": "active" if action == "resume" else "cancelled"}
        elif action == "update":
            recipients = (
                self._lab_recipients(recipient_user_ids, schedule.tool_id)
                if recipient_user_ids
                else schedule.recipient_ids
            )
            frequency = frequency or schedule.frequency
            hour, minute = schedule._lab_hour_minute()
            values = self._lab_schedule_values(
                schedule.tool_id,
                period or schedule.period,
                frequency,
                time or "%02d:%02d" % (hour, minute),
                weekday or schedule.weekday,
                day_of_month or schedule.day_of_month,
                schedule.property_ids.ids,
                schedule.salesperson_ids.ids,
                recipients,
            )
            changes = {
                key: values[key]
                for key in ("period", "frequency", "weekday", "day_of_month")
                if values[key]
                != (schedule[key] or (0 if key == "day_of_month" else False))
            }
            if values["time_of_day"] != schedule.time_of_day:
                changes["time_of_day"] = values["time_of_day"]
            if recipient_user_ids and set(recipients.ids) != set(
                schedule.recipient_ids.ids
            ):
                changes["recipient_ids"] = recipients.ids
            if not changes:
                raise UserError(_("Nothing to change."))
        draft_values = {
            "tool_id": schedule.tool_id.id,
            "period": schedule.period,
            "frequency": schedule.frequency,
            "weekday": schedule.weekday,
            "day_of_month": schedule.day_of_month,
            "time_of_day": schedule.time_of_day,
            "tz": schedule.tz,
        }
        draft_values.update(
            {key: value for key, value in changes.items() if key in draft_values}
        )
        draft = schedule.new(draft_values)
        return {
            "summary": _("%(action)s the report %(name)s.")
            % {"action": _label(action), "name": schedule.name},
            "result": {
                "schedule": self._lab_describe(schedule),
                "changes": dict(
                    changes,
                    next_runs=draft._lab_next_runs(3)
                    if action in ("update", "resume")
                    else None,
                ),
            },
            # Not write_date: the dispatcher writes on every run, and a run
            # between preview and confirm would refuse the confirmation.
            "binding": {
                "schedule": schedule.id,
                "current": {
                    key: schedule[key]
                    for key in (
                        "state",
                        "period",
                        "frequency",
                        "weekday",
                        "day_of_month",
                        "time_of_day",
                    )
                },
                "recipients": schedule.recipient_ids.ids,
                "action": action,
                "changes": changes,
            },
            "plan": {"schedule": schedule.id, "action": action, "changes": changes},
        }

    def _ai_lab_report_schedule_manage_apply(self, plan, **arguments):
        self._lab_check()
        schedule = self.env["alda.ai.lab.schedule"].sudo().browse(plan["schedule"])
        changes = dict(plan["changes"])
        if "recipient_ids" in changes:
            changes["recipient_ids"] = [(6, 0, changes["recipient_ids"])]
        if plan["action"] == "send_now":
            sent = schedule._lab_send()
            summary = (
                _("Report sent to the chat with OdooBot.")
                if sent
                else _("The report failed: %s") % schedule.last_error
            )
        else:
            schedule.write(changes)
            if schedule.state == "active":
                self._lab_ensure_dispatcher()
                schedule._lab_set_next_run(fields.Datetime.now())
            summary = _("Report %(id)s: %(name)s, %(state)s.") % {
                "id": schedule.id,
                "name": schedule.name,
                "state": dict(schedule._fields["state"].selection)[schedule.state],
            }
        return {
            "summary": summary,
            "result": {
                "schedule": self._lab_describe(schedule),
                "next_runs": schedule._lab_next_runs(3)
                if schedule.state == "active"
                else [],
            },
        }
