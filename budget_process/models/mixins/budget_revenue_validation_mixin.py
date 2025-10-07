# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class BudgetRevenueValidationMixin(models.AbstractModel):
    "Mixin for budget record type validation methods"
    _name = "budget.revenue.validation.mixin"
    _description = "Budget Revenue Validation Mixin"

    def _is_rooms_available_budgeted(self):
        return (
            self.record_type in ["rooms_available", "rooms_available_ly"]
            and self.budget_type == "budgeted"
        )

    def _is_room_nights_budgeted(self):
        return self.record_type == "rn_ly" and self.budget_type == "budgeted"

    def _is_increase_decrease_rn_ly_budgeted(self):
        return self.record_type == "increase_decrease_rn_ly" and self.budget_type in [
            "budgeted",
            "real",
        ]

    def _is_rn_budgeted(self):
        return self.record_type == "rn_budgeted" and self.budget_type == "budgeted"
