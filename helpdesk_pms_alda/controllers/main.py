from odoo import http
from odoo.http import request


class HelpdeskFormController(http.Controller):
    @http.route("/helpdesk/ticket/new", type="http", auth="public", website=True)
    def helpdesk_ticket_form(self, **kwargs):
        # Obtener parámetros de la URL
        user_id = int(kwargs.get("user_id"))
        property_id = kwargs.get("property_id")
        team = kwargs.get("team")
        access_token = kwargs.get("access_token")

        # Validar los parámetros ###
        ticket_class_ids = request.env["helpdesk.ticket.class"].sudo().search([])
        user = request.env["res.users"].sudo().browse(int(user_id))
        partner_id = user.partner_id.id if user.partner_id else None
        partner = request.env["res.partner"].sudo().browse(int(partner_id))
        property_id = request.env["pms.property"].sudo().browse(int(property_id))
        team = request.env["helpdesk.team"].sudo().browse(int(team))

        return request.render(
            "helpdesk_pms_alda.create_ticket_form",
            {
                "portal_user_id": user.id,
                "user_name": user.name,
                "team_id": team.id,
                "partner_name": partner.company_name,
                "partner_id": partner.id,
                "property_id": property_id.id,
                "ticket_class_ids": ticket_class_ids,
                "access_token": access_token,
                "team": team.name,
            },
        )

    @http.route(
        "/helpdesk/ticket/submit",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def helpdesk_ticket_submit(self, **post):
        # Crear ticket
        """ticket = (
            request.env["helpdesk.ticket"]
            .sudo()
            .create(
                {
                    "name": post.get("subject"),
                    "partner_id": int(post.get("partner_id")),
                    "partner_name": post.get("partner_name"),
                    "pms_property_id": int(post.get("property_id"))
                    if post.get("property_id")
                    else False,
                    "team_id": int(post.get("team_id"))
                    if post.get("team_id")
                    else False,
                    "ticket_class_id": int(post.get("ticket_class_id")),
                    "description": post.get("description"),
                }
            )
        )"""

        return request.redirect("/helpdesk/ticket/thankyou")

    @http.route("/helpdesk/ticket/thankyou", type="http", auth="public", website=True)
    def helpdesk_ticket_thankyou(self, **kwargs):
        return request.render("helpdesk_pms_alda.thank_you_page")

    # @http.route(
    #    "/helpdesk/ticket/submit",
    #    type="http",
    #    auth="public",
    #    website=True,
    #    methods=["POST"],
    #    csrf=True,
    # )
    # def helpdesk_ticket_submit(self, **post):
    # Descomentar cuando esté lista la lógica de creación
    # ticket = request.env["helpdesk.ticket"].sudo().create(
    #     {
    #         "name": post.get("subject"),
    #         "partner_id": int(post.get("partner_id")),
    #         "partner_name": post.get("partner_name"),
    #         "pms_property_id": int(post.get("property_id"))
    #           if post.get("property_id") else False,
    #         "team_id": int(post.get("team_id")) if post.get("team_id") else False,
    #         "ticket_class_id": int(post.get("ticket_class_id")),
    #         "description": post.get("description"),
    #     }
    # )

    #    return request.redirect("/helpdesk/ticket/thankyou")
