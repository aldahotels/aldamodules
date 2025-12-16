from markupsafe import Markup

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.osv.expression import AND, OR
from odoo.tools import groupby as groupbyelem
from odoo.tools.translate import _

from odoo.addons.helpdesk.controllers.portal import (
    CustomerPortal as HelpdeskCustomerPortal,
)
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PmsHelpdeskTicketClose(HelpdeskCustomerPortal):
    def _get_searchbar_sortings(self):
        return {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "reference": {"label": _("Reference"), "order": "id"},
            "name": {"label": _("Subject"), "order": "name"},
            "user": {"label": _("Assigned to"), "order": "user_id"},
            "stage": {"label": _("Stage"), "order": "stage_id"},
            "pms_property_id": {"label": _("Property"), "order": "name"},
            "team": {"label": _("Team"), "order": "team_id"},
            "room_blocked": {
                "label": _("Room Blocked"),
                "order": "is_room_blocked desc",
            },
            "update": {
                "label": _("Last Stage Update"),
                "order": "date_last_stage_update desc",
            },
        }

    def _get_searchbar_filters(self):
        return {
            "all": {"label": _("All"), "domain": []},
            "assigned": {"label": _("Assigned"), "domain": [("user_id", "!=", False)]},
            "unassigned": {
                "label": _("Unassigned"),
                "domain": [("user_id", "=", False)],
            },
            "open": {"label": _("Open"), "domain": [("close_date", "=", False)]},
            "closed": {"label": _("Closed"), "domain": [("close_date", "!=", False)]},
            "pms_property_id": {
                "label": _("Property"),
                "domain": [("pms_property_id", "!=", False)],
            },
            "team": {"label": _("Team"), "domain": [("team_id", "!=", False)]},
            "room_blocked": {
                "label": _("Room Blocked"),
                "domain": [("is_room_blocked", "=", True)],
            },
        }

    def _get_searchbar_inputs(self):
        return {
            "content": {
                "input": "content",
                "label": Markup(_('Search <span class="nolabel"> (in Content)</span>')),
            },
            "ticket_ref": {"input": "ticket_ref", "label": _("Search in Reference")},
            "message": {"input": "message", "label": _("Search in Messages")},
            "user": {"input": "user", "label": _("Search in Assigned to")},
            "status": {"input": "status", "label": _("Search in Stage")},
            "pms_property_id": {
                "input": "pms_property_id",
                "label": _("Search in Property"),
            },
            "team": {"input": "team_id", "label": _("Search in Team")},
        }

    def _get_searchbar_groupby(self):
        return {
            "none": {"input": "none", "label": _("None")},
            "stage": {"input": "stage_id", "label": _("Stage")},
            "user": {"input": "user_id", "label": _("Assigned to")},
            "pms_property_id": {"input": "pms_property_id", "label": _("Property")},
            "team_id": {"input": "team_id", "label": _("Team")},
            "is_room_blocked": {"input": "is_room_blocked", "label": _("Room Blocked")},
        }

    def _apply_text_search_filter(self, domain, search, search_in):
        if not search or not search_in:
            return domain

        search_domain = []
        if search_in == "ticket_ref":
            search_domain = OR([search_domain, [("ticket_ref", "ilike", search)]])
        if search_in == "content":
            search_domain = OR(
                [
                    search_domain,
                    ["|", ("name", "ilike", search), ("description", "ilike", search)],
                ]
            )
        if search_in == "user":
            assignees = (
                request.env["res.users"].sudo()._search([("name", "ilike", search)])
            )
            search_domain = OR([search_domain, [("user_id", "in", assignees)]])
        if search_in == "pms_property_id":
            props = (
                request.env["pms.property"].sudo()._search([("name", "ilike", search)])
            )
            search_domain = OR([search_domain, [("pms_property_id", "in", props)]])
        if search_in == "team_id":
            teams = (
                request.env["helpdesk.team"].sudo()._search([("name", "ilike", search)])
            )
            search_domain = OR([search_domain, [("team_id", "in", teams)]])
        if search_in == "message":
            discussion_subtype_id = request.env.ref("mail.mt_comment").id
            search_domain = OR(
                [
                    search_domain,
                    [
                        ("message_ids.body", "ilike", search),
                        ("message_ids.subtype_id", "=", discussion_subtype_id),
                    ],
                ]
            )
        if search_in == "status":
            search_domain = OR([search_domain, [("stage_id", "ilike", search)]])

        return AND([domain, search_domain])

    def _perform_grouping(self, tickets, groupby, searchbar_groupby):
        if groupby == "none":
            return [tickets]

        group_key = searchbar_groupby[groupby]["input"]

        def get_group_value(ticket):
            if group_key == "is_room_blocked":
                if ticket.is_room_blocked:
                    return "Blocked"
                elif ticket.pms_room_id:
                    return "Available"
                else:
                    return "No room related"
            val = getattr(ticket, group_key)
            if hasattr(val, "id"):
                return val.id
            return val or "Undefined"

        return [
            request.env["helpdesk.ticket"].concat(*g)
            for key, g in groupbyelem(tickets, key=get_group_value)
        ]

    def _prepare_my_tickets_values(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby="all",
        search=None,
        groupby="none",
        search_in="content",
    ):
        values = self._prepare_portal_layout_values()
        domain = self._prepare_helpdesk_tickets_domain()

        searchbar_sortings = self._get_searchbar_sortings()
        searchbar_filters = self._get_searchbar_filters()
        searchbar_inputs = self._get_searchbar_inputs()
        searchbar_groupby = self._get_searchbar_groupby()

        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        if groupby in searchbar_groupby and groupby != "none":
            order = f'{searchbar_groupby[groupby]["input"]}, {order}'

        domain = AND([domain, searchbar_filters.get(filterby, {}).get("domain", [])])

        if date_begin and date_end:
            domain = AND(
                [
                    domain,
                    [("create_date", ">", date_begin), ("create_date", "<=", date_end)],
                ]
            )

        domain = self._apply_text_search_filter(domain, search, search_in)

        tickets_count = request.env["helpdesk.ticket"].search_count(domain)
        pager = portal_pager(
            url="/my/tickets",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "search_in": search_in,
                "search": search,
                "groupby": groupby,
                "filterby": filterby,
            },
            total=tickets_count,
            page=page,
            step=self._items_per_page,
        )
        tickets = request.env["helpdesk.ticket"].search(
            domain, order=order, limit=self._items_per_page, offset=pager["offset"]
        )
        request.session["my_tickets_history"] = tickets.ids[:100]

        grouped_tickets = self._perform_grouping(tickets, groupby, searchbar_groupby)

        values.update(
            {
                "date": date_begin,
                "grouped_tickets": grouped_tickets,
                "page_name": "ticket",
                "default_url": "/my/tickets",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_filters": searchbar_filters,
                "searchbar_inputs": searchbar_inputs,
                "searchbar_groupby": searchbar_groupby,
                "sortby": sortby,
                "groupby": groupby,
                "search_in": search_in,
                "search": search,
                "filterby": filterby,
                "current_user_id": request.env.user.id,
            }
        )
        return values

    @http.route(
        [
            "/helpdesk/ticket/<int:ticket_id>",
            "/helpdesk/ticket/<int:ticket_id>/<access_token>",
            "/my/ticket/<int:ticket_id>",
            "/my/ticket/<int:ticket_id>/<access_token>",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def tickets_followup(self, ticket_id=None, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access(
                "helpdesk.ticket", ticket_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._ticket_get_page_view_values(ticket_sudo, access_token, **kw)
        values["current_user_id"] = request.env.user.id
        return request.render("helpdesk.tickets_followup", values)

    @http.route(
        [
            "/my/ticket/close/<int:ticket_id>",
            "/my/ticket/close/<int:ticket_id>/<access_token>",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def ticket_close(self, ticket_id=None, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access(
                "helpdesk.ticket", ticket_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        user = request.env.user
        is_technician = user == ticket_sudo.user_id

        if (
            not ticket_sudo.team_id.allow_portal_ticket_closing and not is_technician
        ) or (
            not ticket_sudo.team_id.allow_portal_ticket_closing_technician
            and is_technician
        ):
            raise UserError(_("The team does not allow ticket closing through portal"))

        if not ticket_sudo.closed_by_partner and request.httprequest.method == "GET":
            closing_stage = ticket_sudo.team_id._get_closing_stage()
            if ticket_sudo.stage_id != closing_stage:
                ticket_sudo.write(
                    {"stage_id": closing_stage[0].id, "closed_by_partner": True}
                )
            else:
                ticket_sudo.write({"closed_by_partner": True})
            if is_technician:
                body = _("Ticket closed by the technician")
            else:
                body = _("Ticket closed by the customer")
            ticket_sudo.with_context(mail_create_nosubscribe=True).message_post(
                body=body, message_type="comment", subtype_xmlid="mail.mt_note"
            )

        return request.redirect("/my/ticket/%s/%s" % (ticket_id, access_token or ""))
