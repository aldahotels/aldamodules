from odoo import api, fields, models


class AccountMoveBudgetLine(models.Model):
    _inherit = "account.move.budget.line"

    # compute field as in account_move_line
    # to be able to filter both objects in mis reports
    analytic_account_ids = fields.Many2many(
        "account.analytic.account", compute="_compute_analytic_account_ids", store=True
    )
    hotel_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Hotel Analytic Account",
        compute="_compute_alda_analytic_accounts",
        store=True,
    )
    project_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Project Analytic Account",
        compute="_compute_alda_analytic_accounts",
        store=True,
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

    @api.depends("analytic_account_id")
    def _compute_alda_analytic_accounts(self):
        """Split analytic_account_id into hotel or project account.

        Budget lines hold a single analytic account, so hotel and project
        fields are mutually exclusive: the single account is classified by
        its plan.  Mirrors the logic in account.move.line for MIS report
        compatibility.
        """
        hotel_plan = self.env.ref(
            "pms.main_pms_analytic_plan", raise_if_not_found=False
        )
        for line in self:
            if line.analytic_account_id and hotel_plan:
                if line.analytic_account_id.plan_id == hotel_plan:
                    line.hotel_analytic_account_id = line.analytic_account_id
                    line.project_analytic_account_id = False
                else:
                    line.hotel_analytic_account_id = False
                    line.project_analytic_account_id = line.analytic_account_id
            else:
                line.hotel_analytic_account_id = False
                line.project_analytic_account_id = False
