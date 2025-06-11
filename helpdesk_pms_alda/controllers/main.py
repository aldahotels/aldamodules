import logging

from werkzeug.exceptions import Unauthorized

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.main import ensure_db

_logger = logging.getLogger(__name__)


class HelpdeskFormController(http.Controller):
    @http.route("/helpdesk/ticket/new", type="http", auth="public", website=True)
    def helpdesk_ticket_form(self, **kwargs):
        ensure_db()
        user_id = kwargs.get("user_id")
        property_id = kwargs.get("property_id")
        team = kwargs.get("team_id")
        access_token = kwargs.get("access_token")

        # if not all([user_id, property_id, team, access_token]):
        #     raise AccessDenied("Faltan parámetros requeridos.")
        user_id = int(user_id)
        property_id = int(property_id)
        team = int(team)
        # try:
        # user_id = int(user_id)
        # property_id = int(property_id)
        # team = int(team)
        # except ValueError:
        #     raise AccessDenied("Something parameters no valides.")

        # Buscar usuario
        user = request.env["res.users"].sudo().browse(user_id)
        # if not user.exists():
        #     raise Unauthorized("User no founded.")
        # if not user_id or not access_token or not property_id or not team:
        #     raise Unauthorized("Missing parameters.")

        # Comprueba que el token coincide y que actualmente la sesión es pública
        cur_user = request.env.user
        if cur_user._is_public() and access_token == user.signup_token:
            # Cierra cualquier sesión previa y autentica al portal_user con su token
            request.session.logout(keep_db=True)
            request.session.authenticate(request.db, user.login, access_token)
        else:
            raise Unauthorized("Token inválido o sesión ya iniciada.")

        # Cargar datos adicionales
        ticket_class_ids = request.env["helpdesk.ticket.class"].sudo().search([])
        partner = user.partner_id
        property_record = request.env["pms.property"].sudo().browse(property_id)
        team_record = request.env["helpdesk.team"].sudo().browse(team)

        return request.render(
            "helpdesk_pms_alda.create_ticket_form",
            {
                "portal_user_id": user.id,
                "user_name": user.name,
                "team_id": team_record.id,
                "partner_name": partner.company_name if partner else "",
                "partner_id": partner.id if partner else None,
                "property_id": property_record.id,
                "ticket_class_ids": ticket_class_ids,
                "access_token": access_token,
                "team": team_record.name,
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
        # Crear ticket en modo sudo
        ensure_db()
        csrf_token = request.csrf_token()
        _logger.info("CSRF Token generado: %s", csrf_token)
        ticket = (
            request.env["helpdesk.ticket"]
            .sudo()
            .create(
                {
                    "name": post.get("subject"),
                    "partner_id": int(post.get("portal_user_id"))
                    if post.get("portal_user_id")
                    else False,
                    "partner_name": post.get("partner_name"),
                    "pms_property_id": int(post.get("property_id")),
                    "team_id": int(post.get("team_id")),
                    "ticket_class_id": int(post.get("ticket_class_id"))
                    if post.get("ticket_class_id")
                    else False,
                    "description": post.get("description"),
                }
            )
        )
        _logger.info("Ticket creado: %s", ticket.id)

        return request.redirect("/helpdesk/ticket/thankyou")

    @http.route("/helpdesk/ticket/thankyou", type="http", auth="public", website=True)
    def helpdesk_ticket_thankyou(self, **kwargs):
        return request.render("helpdesk_pms_alda.thank_you_page")
