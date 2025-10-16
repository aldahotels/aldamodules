from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.helpdesk.controllers.portal import (
    CustomerPortal as HelpdeskCustomerPortal,
)


class PmsHelpdeskTicketClose(HelpdeskCustomerPortal):  # noqa: C901
    def _prepare_my_tickets_values(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        groupby="none",
        search=None,
        search_in="content",
        **kw
    ):
        """Preparar valores para la vista de tickets"""
        values = {
            "page": page,
            "date": date_begin,
            "sortby": sortby,
            "filterby": filterby,
            "groupby": groupby,
            "search_in": search_in,
            "search": search,
        }

        if date_begin and date_end:
            values["date_end"] = date_end

        # Searchbar configurations
        searchbar_sortings = self._get_searchbar_sortings()
        searchbar_inputs = self._get_searchbar_inputs()
        searchbar_filters = self._get_searchbar_filters()
        searchbar_groupby = self._get_groupby_options()

        # Base domain
        domain = self._get_base_domain()

        # Apply date filter
        domain = self._apply_date_filter(domain, date_begin, date_end)

        # Apply search filter
        domain = self._apply_search_filter(domain, search_in, search)

        # Apply additional filters
        domain = self._apply_additional_filters(domain, filterby, searchbar_filters)

        # Get tickets with sorting
        tickets = self._get_tickets_with_sorting(domain, sortby, searchbar_sortings)

        # Setup pager
        pager_values = self._setup_pager(tickets, page, values)

        # Prepare final values
        final_values = self._prepare_final_values(
            values,
            tickets,
            searchbar_sortings,
            searchbar_inputs,
            searchbar_filters,
            searchbar_groupby,
            pager_values,
        )

        return final_values

    def _get_base_domain(self):
        """Get base domain for tickets"""
        return [("partner_id", "child_of", request.env.user.partner_id.id)]

    def _apply_date_filter(self, domain, date_begin, date_end):
        """Apply date filter to domain"""
        if date_begin and date_end:
            domain.append(("create_date", ">=", date_begin))
            domain.append(("create_date", "<=", date_end))
        return domain

    def _apply_search_filter(self, domain, search_in, search):
        """Apply search filter to domain"""
        if search and search_in:
            search_domain = []
            if search_in in ("content", "all"):
                search_domain.append(
                    ["|", ("name", "ilike", search), ("description", "ilike", search)]
                )
            if search_in in ("customer", "all"):
                search_domain.append([("partner_id", "ilike", search)])
            if search_in in ("message", "all"):
                search_domain.append([("message_ids.body", "ilike", search)])
            if search_in in ("stage", "all"):
                search_domain.append([("stage_id", "ilike", search)])
            if search_in in ("user", "all"):
                search_domain.append([("user_id", "ilike", search)])
            if search_domain:
                domain += search_domain
        return domain

    def _apply_additional_filters(self, domain, filterby, searchbar_filters):
        """Apply additional filters to domain"""
        if filterby and filterby != "all":
            domain += searchbar_filters[filterby]["domain"]
        return domain

    def _get_tickets_with_sorting(self, domain, sortby, searchbar_sortings):
        """Get tickets with applied sorting"""
        sort_order = searchbar_sortings.get(sortby, searchbar_sortings["create_date"])[
            "order"
        ]
        return request.env["helpdesk.ticket"].sudo().search(domain, order=sort_order)

    def _setup_pager(self, tickets, page, values):
        """Setup pager for tickets"""
        ticket_count = len(tickets)
        pager = request.website.pager(
            url="/my/tickets",
            url_args=values,
            total=ticket_count,
            page=page,
            step=self._items_per_page,
        )
        paged_tickets = tickets[
            (page - 1) * self._items_per_page : page * self._items_per_page
        ]
        return {"pager": pager, "tickets": paged_tickets, "ticket_count": ticket_count}

    def _prepare_final_values(
        self,
        values,
        tickets,
        searchbar_sortings,
        searchbar_inputs,
        searchbar_filters,
        searchbar_groupby,
        pager_values,
    ):
        """Prepare final values dictionary"""
        values.update(
            {
                "tickets": pager_values["tickets"],
                "page_name": "ticket",
                "pager": pager_values["pager"],
                "default_url": "/my/tickets",
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "searchbar_filters": searchbar_filters,
                "ticket_count": pager_values["ticket_count"],
            }
        )

        # Group tickets if needed
        if values["groupby"] != "none":
            values["grouped_tickets"] = self._group_tickets(
                pager_values["tickets"], values["groupby"]
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
