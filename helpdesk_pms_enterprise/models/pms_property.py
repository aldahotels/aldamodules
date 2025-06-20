from odoo import api, fields, models


class PmsProperty(models.Model):
    _inherit = "pms.property"

    ticket_count = fields.Integer(
        string="Tickets", compute="_compute_ticket_count", store=True
    )

    @api.depends("helpdesk_ticket_ids")
    def _compute_ticket_count(self):
        for prop in self:
            prop.ticket_count = self.env["helpdesk.ticket"].search_count(
                [("pms_property_id", "=", prop.id)]
            )

    helpdesk_ticket_ids = fields.One2many(
        "helpdesk.ticket", "pms_property_id", string="Tickets"
    )

    def action_view_tickets(self):
        self.ensure_one()
        action = (
            self.env.ref("helpdesk_pms_enterprise.action_helpdesk_ticket")
            .sudo()
            .read()[0]
        )
        action["domain"] = [("pms_property_id", "=", self.id)]
        action["context"] = {"create": False}
        return action
