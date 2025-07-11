import logging

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.utils import ensure_db

_logger = logging.getLogger(__name__)


class HelpdeskFormController(http.Controller):
    @http.route("/helpdesk/ticket/new", type="http", auth="public", website=True)
    def helpdesk_ticket_form(self, **kwargs):
        ensure_db()
        user_id = request.env.user
        partner_id = request.env.user.partner_id
        property_id = int(kwargs.get("property_id", 0))

        property_record = request.env["pms.property"].sudo().browse(property_id)
        company_id = user_id.company_id.id if user_id.company_id else False

        team_ids = (
            request.env["helpdesk.team"]
            .sudo()
            .search(["|", ("company_id", "=", False), ("company_id", "=", company_id)])
        )
        ticket_type_ids = (
            request.env["helpdesk.ticket.type"]
            .sudo()
            .search([("team_id", "in", team_ids.ids)])
        )
        is_overnight_room = (
            request.env["pms.room.type"]
            .sudo()
            .search([("overnight_room", "=", True)])
            .ids
        )
        room_ids = (
            request.env["pms.room"]
            .sudo()
            .search(
                [
                    ("pms_property_id", "=", property_record.id),
                    ("room_type_id", "in", is_overnight_room),
                    ("active", "=", True),
                ]
            )
        )

        location_type_options = request.env["helpdesk.ticket"]._get_location_selection()
        room_state_ids = {}
        for room in room_ids:
            room_state_ids[room.id] = (
                request.env["helpdesk.ticket"].sudo()._is_room_blocked(room)
            )

        company_external_id = False

        return request.render(
            "alda_helpdesk_pms.create_ticket_form",
            {
                "portal_user_id": user_id.id,
                "user_name": user_id.name,
                "team_ids": team_ids,
                "ticket_type_ids": ticket_type_ids,
                "partner_name": partner_id.company_name if partner_id else "",
                "partner_id": partner_id.id if partner_id else None,
                "property_id": property_record.id,
                "property_name": property_record.name,
                "room_ids": room_ids,
                "is_room": False,
                "location_type_options": location_type_options,
                "is_room_blocked_ids": room_state_ids,
                "company_external_id": company_external_id,
            },
        )

    @http.route(
        "/helpdesk/ticket/submit",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def helpdesk_ticket_submit(self, **post):
        ensure_db()
        room_id = post.get("room_ids", "")
        ticket_type_id = post.get("ticket_type_id", "")
        pms_room_id = int(room_id) if room_id else False

        ticket = (
            request.env["helpdesk.ticket"]
            .sudo()
            .create(
                {
                    "name": post.get("subject"),
                    "partner_id": int(post.get("partner_id")),
                    "partner_name": post.get("partner_name"),
                    "pms_property_id": int(post.get("property_id")),
                    "team_id": int(post.get("team_id")),
                    "ticket_type_id": ticket_type_id,
                    "location_type": post.get("location_type"),
                    "pms_room_id": pms_room_id,
                    "company_external_id": post.get("company_external_id"),
                    "description": post.get("description"),
                }
            )
        )
        _logger.info("Ticket creado: %s", ticket.id)

        return request.redirect("/helpdesk/ticket/thankyou")

    @http.route("/helpdesk/ticket/thankyou", type="http", auth="public", website=True)
    def helpdesk_ticket_thankyou(self, **kwargs):
        return request.render("alda_helpdesk_pms.thank_you_page")
