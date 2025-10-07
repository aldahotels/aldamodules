# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetRevenuePercentageActionsMixin(models.AbstractModel):
    "Mixin for percentage-related actions"
    _name = "budget.revenue.percentage.actions.mixin"
    _description = "Budget Revenue Percentage Actions Mixin"

    def action_apply_percentage_to_months(self):
        "Apply percentage to all monthly fields for increase/decrease RN LY records"
        updated_count = 0

        for record in self:
            if record._is_increase_decrease_rn_ly_budgeted():
                if not record.fiscal_year_id:
                    _logger.warning(
                        "Record %s missing fiscal_year_id, skipping", record.id
                    )
                    continue

                percentage_value = record.percentage_increase_decrease or 0.0
                monthly_updates = {month: percentage_value for month in MONTHLY_FIELDS}

                record.write(monthly_updates)
                updated_count += 1

                _logger.info(
                    "Applied %s%% to all months for record %s (%s)",
                    percentage_value,
                    record.id,
                    record.hotel.name if record.hotel else "No Hotel",
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Percentage Applied",
                "message": (
                    "Applied percentage to %s increase/decrease RN LY records"
                    % updated_count
                ),
                "type": "success",
                "sticky": True,
            },
        }
