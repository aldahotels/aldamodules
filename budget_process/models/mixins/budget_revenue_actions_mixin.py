# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class BudgetRevenueActionsMixin(models.AbstractModel):
    "Mixin for diagnostic and debugging action for revenue"
    _name = "budget.revenue.actions.mixin"
    _description = "Budget Revenue Actions Mixin"
    _inherit = [
        "budget.rooms.base.actions.mixin",
        "budget.pax.base.actions.mixin",
        "budget.revenue.occ.compute.mixin",
    ]

    def action_refresh_rooms_available(self):
        return self.action_refresh_rooms_available_base("[REVENUE]")

    def action_sync_all_rooms_available(self):
        return self.action_sync_all_rooms_available_base(
            "[REVENUE]", ["rooms_available_ly"]
        )

    def action_show_sync_status(self):
        return self.action_show_sync_status_base("[REVENUE]")

    def action_diagnose_current_records(self):
        return self.action_diagnose_current_records_base("[REVENUE]")

    def action_fix_sync_problems(self):
        return self.action_fix_sync_problems_base("[REVENUE]")

    def action_diagnose_pax_budgeted_formula(self):
        return self.action_diagnose_pax_budgeted_formula_base("[REVENUE]")
