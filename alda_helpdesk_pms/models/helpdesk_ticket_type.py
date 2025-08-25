from odoo import fields, models


class HelpdeskTicketType(models.Model):
    _inherit = "helpdesk.ticket.type"

    team_id = fields.Many2one(
        comodel_name="helpdesk.team",
        string="Team",
        help="The team to which this ticket type belongs.",
    )

    color = fields.Integer(
        help="Color associated with the ticket type.",
    )
