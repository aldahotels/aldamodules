from odoo import api, fields, models


class HelpdeskTicketClass(models.Model):
    _name = "helpdesk.ticket.class"
    _description = "Class of Helpdesk Ticket"
    _order = "name"

    name = fields.Char(string="Class", required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(
        help="Color associated with the ticket class",
    )
    ticket_type_ids = fields.One2many(
        comodel_name="helpdesk.ticket.type",
        inverse_name="ticket_class_id",
        string="Ticket Types",
    )

    _sql_constraints = [
        ("name_uniq", "unique (name)", "A type with the same name already exists."),
    ]

    # Campo virtual para mostrar tags
    ticket_type_tag_ids = fields.Many2many(
        "helpdesk.ticket.type",
        string="Tipos de Ticket",
        compute="_compute_ticket_type_tag_ids",
    )

    @api.depends("ticket_type_ids")
    def _compute_ticket_type_tag_ids(self):
        for record in self:
            record.ticket_type_tag_ids = record.ticket_type_ids
