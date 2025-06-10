from odoo import fields, models


class HelpdeskTicketType(models.Model):
    _inherit = "helpdesk.ticket.type"

    ticket_class_id = fields.Many2one(
        comodel_name="helpdesk.ticket.class",
        string="Ticket Class",
        help="The class to which this ticket type belongs.",
        required=True,
    )
    color = fields.Integer(
        help="Color associated with the ticket type.",
    )
