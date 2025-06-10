from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    ticket_class_id = fields.Many2one(
        comodel_name="helpdesk.ticket.class",
        string="Ticket Class",
        help="The class to which this ticket belongs.",
        tracking=True,
    )

    ticket_type_id = fields.Many2one(
        comodel_name="helpdesk.ticket.type",
        string="Type",
        tracking=True,
        domain="[('ticket_class_id', '=', ticket_class_id)]",
        help="The type of ticket, which determines its specific characteristics and workflow.",
    )

    @api.onchange("ticket_class_id")
    def _onchange_ticket_class(self):
        self.ticket_type_id = False
        if self.ticket_class_id:
            return {
                "domain": {
                    "ticket_type_id": [
                        ("ticket_class_id", "=", self.ticket_class_id.id)
                    ]
                }
            }
        else:
            return {"domain": {"ticket_type_id": []}}
