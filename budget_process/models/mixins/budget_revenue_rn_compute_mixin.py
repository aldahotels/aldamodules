# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetRevenueRNComputeMixin(models.AbstractModel):
    "Mixin for budget computation methods"
    _name = "budget.revenue.rn.compute.mixin"
    _description = "Budget Compute Mixin"

    def _get_rooms_nights_from_budget_data(self):
        "Get room nights data from budget.data model"
        return self._get_budget_data_values("rn_ly", "room_nights_real")

    def _get_increase_decrease_rn_ly_values(self):
        "Get percentage values for increase/decrease RN LY"
        monthly_values = {month: 0 for month in MONTHLY_FIELDS}

        if self._is_increase_decrease_rn_ly_budgeted():
            percentage_value = self.percentage_increase_decrease or 0.0

            for month in MONTHLY_FIELDS:
                monthly_values[month] = percentage_value

            _logger.info(
                "Applied percentage %s%% to all months for %s (fiscal %s)",
                percentage_value,
                self.hotel.name if self.hotel else "No Hotel",
                self.fiscal_year_id.name if self.fiscal_year_id else "No Fiscal Year",
            )

        return monthly_values

    def _get_rn_budgeted_values(self):
        """
        Calculate RN Budgeted:
        min(rn_ly*(1+increase_decrease_rn_ly), rooms_available)
        """
        monthly_values = {month: 0 for month in MONTHLY_FIELDS}

        if not self._is_rn_budgeted():
            return monthly_values

        if not (self.hotel and self.fiscal_year_id and self.budget_type):
            _logger.warning(
                "RN Budgeted calculation requires hotel, fiscal_year_id and budget_type"
            )
            return monthly_values

        # Get previous fiscal year for rn_ly and increase_decrease_rn_ly
        current_fiscal_year = self.fiscal_year_id
        previous_fiscal_year = self._get_previous_fiscal_year(current_fiscal_year)

        # Domain for records from previous fiscal year (rn_ly and increase_decrease)
        previous_year_domain = [
            ("hotel", "=", self.hotel.id),
            ("budget_type", "=", "budgeted"),
        ]

        # Domain for records from SAME fiscal year (rooms_available)
        same_year_domain = [
            ("hotel", "=", self.hotel.id),
            ("fiscal_year_id", "=", self.fiscal_year_id.id),
            ("budget_type", "=", "budgeted"),
        ]

        # Add previous fiscal year filter if it exists
        if previous_fiscal_year:
            previous_year_domain.append(
                ("fiscal_year_id", "=", previous_fiscal_year.id)
            )
        else:
            _logger.warning(
                "No previous fiscal year found for %s. Cannot calculate RN Budgeted.",
                current_fiscal_year.name,
            )
            return monthly_values

        # Get required records
        rn_ly_record = self.env["budget.revenue"].search(
            previous_year_domain + [("record_type", "=", "rn_ly")], limit=1
        )
        increase_decrease_record = self.env["budget.revenue"].search(
            previous_year_domain + [("record_type", "=", "increase_decrease_rn_ly")],
            limit=1,
        )
        rooms_available_record = self.env["budget.revenue"].search(
            same_year_domain + [("record_type", "=", "rooms_available")], limit=1
        )

        # Check if all required records exist
        missing_records = []
        missing_details = []

        if not rn_ly_record:
            missing_records.append("rn_ly")
            missing_details.append(
                f"rn_ly (budgeted) for {self.hotel.name} "
                f"in fiscal year {previous_fiscal_year.name}"
            )

        if not increase_decrease_record:
            missing_records.append("increase_decrease_rn_ly")
            missing_details.append(
                f"increase_decrease_rn_ly (budgeted) for {self.hotel.name} "
                f"in fiscal year {previous_fiscal_year.name}"
            )

        if not rooms_available_record:
            missing_records.append("rooms_available")
            missing_details.append(
                f"rooms_available (budgeted) for {self.hotel.name} "
                f"in fiscal year {current_fiscal_year.name}"
            )

        if missing_records:
            _logger.warning(
                "RN Budgeted calculation failed for %s (fiscal %s): Missing records: %s",
                self.hotel.name,
                current_fiscal_year.name,
                ", ".join(missing_details),
            )
            return monthly_values

        # Calculate formula for each month
        for month in MONTHLY_FIELDS:
            rn_ly_value = getattr(rn_ly_record, month, 0) or 0
            increase_percentage = getattr(increase_decrease_record, month, 0) or 0
            rooms_available_value = getattr(rooms_available_record, month, 0) or 0

            # Formula
            adjusted_rn = rn_ly_value * (1 + (increase_percentage / 100))

            # Apply min() function with rooms_available
            final_value = min(adjusted_rn, rooms_available_value)
            monthly_values[month] = final_value

            _logger.info(
                (
                    "RN Budgeted %s: rn_ly=%s (from %s), increase=%s%% (from %s),"
                    " rooms_available=%s (from %s) min(%s, %s) = %s",
                ),
                month,
                rn_ly_value,
                previous_fiscal_year.name,
                increase_percentage,
                previous_fiscal_year.name,
                rooms_available_value,
                current_fiscal_year.name,
                adjusted_rn,
                rooms_available_value,
                final_value,
            )

        _logger.info(
            "RN Budgeted calculation completed for %s (fiscal %s) using data from fiscal %s",
            self.hotel.name,
            current_fiscal_year.name,
            previous_fiscal_year.name,
        )

        return monthly_values
