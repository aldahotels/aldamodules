


from odoo import api, fields, models


class AccountMoveBudgetLine(models.Model):
    _inherit = "account.move.budget.line"

    # compute field as in account_move_line
    # to be able to filter both objects in mis reports
    analytic_account_ids = fields.Many2many(
        "account.analytic.account", compute="_compute_analytic_account_ids", store=True
    )

    @api.depends("analytic_account_id")
    def _compute_analytic_account_ids(self):
        for line in self:
            if not line.analytic_account_id:
                line.analytic_account_ids = False
            else:
                line.analytic_account_ids = [
                    fields.Command.link(line.analytic_account_id.id)
                ]

