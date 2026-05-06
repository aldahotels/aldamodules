# © 2024 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    """Extend account.move.line with hotel/project analytic account helpers.

    These computed stored fields split the analytic_distribution dict into the
    two analytic plans used in the PMS context:

    - hotel_analytic_account_id: the account belonging to the PMS "Properties"
      plan (pms.main_pms_analytic_plan).  There should always be one when
      analytic_distribution is set.
    - project_analytic_account_id: the first account that does NOT belong to
      the PMS plan (e.g. the sub-project analytic for Carballo).
    """

    _inherit = "account.move.line"

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

    @api.depends("analytic_distribution")
    def _compute_alda_analytic_accounts(self):
        """Split analytic_distribution into hotel and project analytic accounts.

        The hotel plan is identified by the pms.main_pms_analytic_plan XML ID.
        If that plan is not installed the field remains empty.  When the
        distribution contains more than one hotel or project account (which
        should not happen), the first one found is used.
        """
        hotel_plan = self.env.ref(
            "pms.main_pms_analytic_plan", raise_if_not_found=False
        )
        for line in self:
            hotel_account = self.env["account.analytic.account"]
            project_account = self.env["account.analytic.account"]
            if line.analytic_distribution and hotel_plan:
                account_ids = [int(k) for k in line.analytic_distribution.keys()]
                accounts = self.env["account.analytic.account"].browse(account_ids)
                for account in accounts:
                    if not hotel_account and account.plan_id == hotel_plan:
                        hotel_account = account
                    elif not project_account and account.plan_id != hotel_plan:
                        project_account = account
                    if hotel_account and project_account:
                        break
            line.hotel_analytic_account_id = hotel_account
            line.project_analytic_account_id = project_account
