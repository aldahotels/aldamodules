# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetRevenuePaxComputeMixin(models.AbstractModel):
    """Mixin for pax budgeted calculations in revenue budget"""

    _name = "budget.revenue.pax.compute.mixin"
    _description = "Budget Revenue Pax Compute Mixin"

    def _get_pax_budgeted_values(self):
        """Get pax budgeted values from budget.data and apply formula with
        previous year increase/decrease"""
        monthly_values = {month: 0 for month in MONTHLY_FIELDS}

        if not (self.hotel and self.fiscal_year_id):
            _logger.warning(
                "PAX BUDGETED: Missing hotel (%s) or fiscal year (%s)",
                self.hotel,
                self.fiscal_year_id,
            )
            return monthly_values

        _logger.info("PAX BUDGETED: Searching budget.data for hotel %s", self.hotel.id)

        # Get previous fiscal year for increase/decrease rate
        previous_fiscal_year = self._get_previous_fiscal_year(self.fiscal_year_id)
        increase_decrease_rate = 0.0

        if previous_fiscal_year:
            # Search for increase_decrease_rn_ly record from previous fiscal year
            previous_year_record = self.env["budget.revenue"].search(
                [
                    ("hotel", "=", self.hotel.id),
                    ("fiscal_year_id", "=", previous_fiscal_year.id),
                    ("record_type", "=", "increase_decrease_rn_ly"),
                    ("budget_type", "=", "budgeted"),
                ],
                limit=1,
            )
            if previous_year_record:
                # Use the percentage_increase_decrease field or calculate
                if (
                    hasattr(previous_year_record, "percentage_increase_decrease")
                    and previous_year_record.percentage_increase_decrease
                ):
                    increase_decrease_rate = (
                        previous_year_record.percentage_increase_decrease / 100.0
                    )
                    _logger.info(
                        "PAX BUDGETED: Found percentage_increase_decrease: %s%% (rate: %s)",
                        previous_year_record.percentage_increase_decrease,
                        increase_decrease_rate,
                    )
                else:
                    # Calculate average from monthly values if percentage field is not available
                    monthly_sum = sum(
                        getattr(previous_year_record, month, 0)
                        for month in MONTHLY_FIELDS
                    )
                    monthly_avg = monthly_sum / 12.0 if monthly_sum else 0.0
                    increase_decrease_rate = monthly_avg / 100.0  # Convert to decimal
                    _logger.info(
                        "PAX BUDGETED: Calculated average rate from monthly "
                        "values: %s%% (rate: %s)",
                        monthly_avg,
                        increase_decrease_rate,
                    )
            else:
                _logger.warning(
                    "PAX BUDGETED: No increase_decrease_rn_ly record found for "
                    "previous fiscal year %s",
                    previous_fiscal_year.name,
                )
        else:
            _logger.warning(
                "PAX BUDGETED: No previous fiscal year found for current year %s",
                self.fiscal_year_id.name,
            )

        try:
            month_year_mapping = self._get_fiscal_month_mapping()

            if not month_year_mapping:
                _logger.info("PAX BUDGETED: No fiscal mapping available")
                return monthly_values

            _logger.info("PAX BUDGETED: Processing 12 months for fiscal mapping")

            for month_field, (
                calendar_year,
                calendar_month,
            ) in month_year_mapping.items():
                _logger.info(
                    "PAX BUDGETED: Processing %s: %s/%02d",
                    month_field,
                    calendar_year,
                    calendar_month,
                )

                budget_data = self.env["budget.data"].search(
                    [
                        ("pms_property_id", "=", self.hotel.id),
                        ("year", "=", str(calendar_year)),
                        ("month", "=", str(calendar_month)),
                    ],
                    limit=1,
                )

                _logger.info(
                    "PAX BUDGETED: Found %s budget.data records for %s/%s",
                    len(budget_data),
                    calendar_year,
                    calendar_month,
                )

                if budget_data and budget_data.total_pax:
                    # Apply formula: pax_budgeted * (1 + increase_decrease_rn_ly)
                    base_pax = budget_data.total_pax
                    adjusted_pax = base_pax * (1 + increase_decrease_rate)
                    monthly_values[month_field] = adjusted_pax

                    _logger.info(
                        "PAX BUDGETED: FORMULA APPLIED: %s = %s * (1 + %s) = %s",
                        month_field,
                        base_pax,
                        increase_decrease_rate,
                        adjusted_pax,
                    )

        except Exception as e:
            _logger.error("PAX BUDGETED: EXCEPTION in _get_pax_budgeted_values: %s", e)

        _logger.info("PAX BUDGETED: RETURNING monthly_values: %s", monthly_values)
        return monthly_values
