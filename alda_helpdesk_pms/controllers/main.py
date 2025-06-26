import logging

import werkzeug
from werkzeug.exceptions import Unauthorized

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.utils import ensure_db

_logger = logging.getLogger(__name__)


class HelpdeskFormController(http.Controller):
    @http.route(
        "/portal_ticket_login_by_token",
        type="http",
        auth="public",
        website=True,
    )
    def portal_ticket_login_by_token(self, **kwargs):
        ensure_db()
        user_id = int(kwargs.get("user_id"))
        property_id = int(kwargs.get("property_id"))
        signup_token = kwargs.get("signup_token")

        if not user_id or not signup_token:
            raise Unauthorized("Wrong authentication")
        portal_user = request.env["res.users"].sudo().browse(user_id)

        if portal_user:
            cur_user = request.env["res.users"].browse(request.env.uid)
            is_public = cur_user._is_public()
            if (
                is_public or cur_user.id != portal_user.id
            ) and signup_token == portal_user.signup_token:
                request.session.logout(keep_db=True)
                request.session.authenticate(
                    request.db, portal_user.login, signup_token
                )
        url = "/helpdesk/ticket/new/?user_id={}&property_id={}&signup_token={}".format(
            user_id, property_id, signup_token
        )
        return werkzeug.utils.redirect(url)

    @http.route("/helpdesk/ticket/new", type="http", auth="public", website=True)
    def helpdesk_ticket_form(self, **kwargs):
        ensure_db()
        user_id = int(kwargs.get("user_id"))
        property_id = int(kwargs.get("property_id"))
        access_token = kwargs.get("signup_token")

        user_id = request.env["res.users"].sudo().browse(user_id)
        partner_id = (
            request.env["res.partner"]
            .sudo()
            .search([("id", "=", user_id.partner_id.id)])
        )
        property_record = request.env["pms.property"].sudo().browse(property_id)
        team_ids = request.env["helpdesk.team"].sudo().search([])
        ticket_type_ids = (
            request.env["helpdesk.ticket.type"]
            .sudo()
            .search([("team_id", "in", team_ids.ids)])
        )
        room_ids = (
            request.env["pms.room"]
            .sudo()
            .search([("pms_property_id", "=", property_record.id)])
        )
        location_type_options = request.env["helpdesk.ticket"]._get_location_selection()
        room_state_ids = {}
        for room in room_ids:
            room_state_ids[room.id] = (
                request.env["helpdesk.ticket"].sudo()._is_room_blocked(room.id)
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
                "access_token": access_token,
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
        post.get("ticket_type_ids", "")
        pms_room_id = int(room_id) if room_id else False
        location_type = post.get("location_type_options")
        bathroom_type = post.get("bathroom_type")
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
                    "ticket_type_id": int(post.get("ticket_type_id")),
                    "location_type": location_type,
                    "bathroom_type": bathroom_type
                    if location_type == "bathroom"
                    else False,
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
