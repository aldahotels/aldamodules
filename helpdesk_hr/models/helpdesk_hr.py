from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrJob(models.Model):
    _inherit = "hr.job"

    ticket_team_id = fields.Many2one(
        comodel_name="helpdesk.team",
        string="Team Helpdesk",
        help="Employee this job position will be related to this helpdesk team.",
    )

    ticket_type_ids = fields.Many2many(
        comodel_name="helpdesk.ticket.type",
        string="Ticket Types",
        help="Ticket types that this job position can handle.",
        default=False,
    )
    is_ticket_type_ids = fields.Boolean(
        string="Team Has Ticket Types",
        compute="_compute_team_has_ticket_types",
        store=False,
        readonly=True,
        help="Indicates if the selected helpdesk team has any ticket types associated.",
    )

    type_avalible = fields.Many2many(
        comodel_name="helpdesk.ticket.type",
        store=False,
        compute="_compute_type_avalible",
    )

    def _compute_type_avalible(self):
        for job in self:
            if job.ticket_team_id:
                job.type_avalible = self.env["helpdesk.ticket.type"].search(
                    [("team_id", "=", job.ticket_team_id.id)]
                )
            else:
                job.type_avalible = [(5, 0, 0)]

    @api.onchange("ticket_team_id")
    def _onchange_ticket_team_id(self):
        if self.ticket_team_id:
            valid_types = self.env["helpdesk.ticket.type"].search(
                [("team_id", "=", self.ticket_team_id.id)]
            )
            if valid_types:
                current_valid = self.ticket_type_ids & valid_types
                self.ticket_type_ids = current_valid
                self.ticket_type_ids = valid_types
                self.ticket_type_ids = [(5, 0, 0)]
                return {
                    "domain": {
                        "ticket_type_ids": [("team_id", "=", self.ticket_team_id.id)]
                    }
                }
            else:
                self.ticket_type_ids = [(5, 0, 0)]
                return {
                    "domain": {"ticket_type_ids": [("id", "=", False)]},
                    "warning": {
                        "title": _("No Ticket Types"),
                        "message": _(
                            "The selected team has no ticket types associated. "
                            "The ticket types selection has been cleared."
                        ),
                    },
                }
        else:
            self.ticket_type_ids = [(5, 0, 0)]
            return {"domain": {"ticket_type_ids": []}}

    @api.depends("ticket_team_id")
    def _compute_team_has_ticket_types(self):
        for job in self:
            if job.ticket_team_id:
                types = self.env["helpdesk.ticket.type"].search(
                    [("team_id", "=", job.ticket_team_id.id)]
                )
                job.is_ticket_type_ids = bool(types)
            else:
                job.is_ticket_type_ids = False

    @api.constrains("ticket_team_id", "ticket_type_ids")
    def _check_ticket_types_team(self):
        for job in self:
            if job.ticket_team_id and job.ticket_type_ids:
                invalid_types = job.ticket_type_ids.filtered(
                    lambda t: t.team_id != job.ticket_team_id
                )
                if invalid_types:
                    raise ValidationError(
                        _(
                            "The following ticket types do not belong to the "
                            "selected helpdesk team: %s"
                        )
                        % ", ".join(invalid_types.mapped("name"))
                    )
