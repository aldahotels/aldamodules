import base64
import logging

from odoo import _, http
from odoo.http import request

from odoo.addons.web.controllers.utils import ensure_db

_logger = logging.getLogger(__name__)


class HelpdeskFormController(http.Controller):
    def _prepare_ticket_vals(self, post):
        room_id = post.get("room_ids", "")
        pms_property = post.get("property_id", "")
        ticket_type_id = post.get("ticket_type_id", "")
        is_property_operated_normaly = post.get("is_property_operated_normaly") == "on"
        pms_room_id = int(room_id) if room_id else False
        reference_data = (post.get("reference_data") or "").strip()

        if reference_data:
            description_text = (
                "\n\n"
                + _("Data reference/reservation number: ")
                + reference_data
                + "\n\n <br/><br/>"
                + post.get("description", "")
            )
            subject_text = post.get("subject", "") + " - Ref: " + reference_data
        else:
            description_text = post.get("description", "")
            subject_text = post.get("subject", "")

        is_room_operated_normaly = True
        if pms_room_id:
            room = request.env["pms.room"].browse(pms_room_id)
            is_room_operated_normaly = (
                not request.env["helpdesk.ticket"].sudo()._is_room_blocked(room)
            )

        vals = {
            "name": subject_text,
            "partner_id": int(post.get("partner_id")),
            "partner_name": post.get("partner_name"),
            "pms_property_id": int(pms_property),
            "team_id": int(post.get("team_id")),
            "ticket_type_id": ticket_type_id,
            "location_type": post.get("location_type"),
            "pms_room_id": pms_room_id,
            "company_external_id": post.get("company_external_id"),
            "description": description_text,
            "priority": post.get("priority"),
            "is_property_operated_normaly": is_property_operated_normaly,
            "is_room_operated_normaly": is_room_operated_normaly,
        }

        return vals

    @http.route("/helpdesk/ticket/property", type="http", auth="public", website=True)
    def helpdesk_ticket_select_property(self, **kwargs):
        ensure_db()

        if not request.env.user.has_group("base.group_user"):
            return request.redirect("/web/login")

        user = request.env.user
        user_properties = user.pms_property_ids.filtered(lambda p: p.active)

        property_id = kwargs.get("property_id")
        if property_id:
            selected_property = (
                request.env["pms.property"].sudo().browse(int(property_id))
            )
            if selected_property and selected_property in user_properties:
                # 🔁 Redirige al formulario de ticket
                return request.redirect(
                    f"/helpdesk/ticket/new?property_id={property_id}"
                )
            else:
                # Si la propiedad no está permitida
                return request.render("alda_helpdesk_pms.property_not_allowed", {})

        return request.render(
            "alda_helpdesk_pms.select_property_form",
            {"properties": user_properties},
        )

    @http.route("/helpdesk/ticket/new", type="http", auth="public", website=True)
    def helpdesk_ticket_form(self, **kwargs):
        ensure_db()
        if not (
            request.env.user.has_group("base.group_user")
            or request.env.user.has_group("base.group_portal")
        ):
            return request.redirect("/web/login")

        user_id = request.env.user
        partner_id = request.env.user.partner_id
        property_id = int(kwargs.get("property_id", 0))

        pms_property_ids = request.env["pms.property"].sudo().browse(property_id)

        visibility_filter = []
        if user_id.has_group("base.group_portal"):
            visibility_filter = ["portal"]
        else:
            visibility_filter = ["portal", "internal", "public"]
        team_ids = (
            request.env["helpdesk.team"]
            .sudo()
            .search(
                [
                    ("privacy_visibility", "in", visibility_filter),
                    ("is_pms_form", "=", True),
                ]
            )
        )

        is_location_required_ids = (
            True if team_ids.filtered(lambda t: t.is_location_required) else False
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
                    ("pms_property_id", "=", pms_property_ids.id),
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
        is_property_operated_normaly = True

        return request.render(
            "alda_helpdesk_pms.create_ticket_form",
            {
                "portal_user_id": user_id.id,
                "user_name": user_id.name,
                "team_ids": team_ids,
                "is_location_required": is_location_required_ids,
                "ticket_type_ids": ticket_type_ids,
                "partner_name": partner_id.company_name if partner_id else "",
                "partner_id": partner_id.id if partner_id else None,
                "property_id": pms_property_ids.id,
                "property_name": pms_property_ids.name,
                "room_ids": room_ids,
                "is_room": False,
                "location_type_options": location_type_options,
                "is_room_blocked_ids": room_state_ids,
                "company_external_id": company_external_id,
                "is_property_operated_normaly": is_property_operated_normaly,
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

        ticket_vals = self._prepare_ticket_vals(post)

        ticket = (
            request.env["helpdesk.ticket"]
            .with_context(from_web_create=True)
            .sudo()
            .create(ticket_vals)
        )

        attachment = request.httprequest.files.get("attachment")
        if post.get("attachment", False):
            attachments = request.httprequest.files.getlist("attachment")
            attachment_ids = []
            for attachment in attachments:
                if attachment and attachment.filename:
                    try:
                        attachment_data = base64.b64encode(attachment.read()).decode(
                            "utf-8"
                        )
                        att = (
                            request.env["ir.attachment"]
                            .sudo()
                            .create(
                                {
                                    "name": attachment.filename,
                                    "type": "binary",
                                    "datas": attachment_data,
                                    "res_model": "helpdesk.ticket",
                                    "res_id": ticket.id,
                                    "public": True,
                                    "mimetype": attachment.content_type,
                                }
                            )
                        )
                        attachment_ids.append(att.id)
                    except Exception as e:
                        _logger.error("Upload file failed %s: %s", ticket.id, str(e))

            if attachment_ids:
                message_body = post.get("description", "")
                ticket.message_post(
                    body=message_body,
                    attachment_ids=attachment_ids,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )

        return request.redirect(f"/helpdesk/ticket/confirmation/{ticket.id}")

    @http.route(
        "/helpdesk/ticket/confirmation/<int:ticket_id>",
        type="http",
        auth="public",
        website=True,
    )
    def helpdesk_ticket_thankyou(self, ticket_id=None, **kwargs):
        values = {
            "ticket": None,
            "ticket_url": None,
        }
        if ticket_id:
            try:
                ticket = request.env["helpdesk.ticket"].sudo().browse(int(ticket_id))
                if ticket.exists():
                    ticket_url = f"/my/ticket/{ticket.id}/{ticket.access_token}"
                    values.update(
                        {
                            "ticket": ticket,
                            "ticket_url": ticket_url,
                        }
                    )
            except Exception as e:
                _logger.error("Error processing ticket confirmation: %s", str(e))

        return request.render("alda_helpdesk_pms.confirmation_ticket", values)
