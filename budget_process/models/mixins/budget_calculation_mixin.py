# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetCalculationMixin(models.AbstractModel):
    "Mixin for budget calculation utilities and common methods"
    _name = "budget.calculation.mixin"
    _description = "Budget Calculation Mixin"

    def _get_fiscal_month_mapping(self):
        "Returns a mapping of fiscal months to (calendar_year, calendar_month)"
        if not self.fiscal_year_id:
            return {}

        fiscal_year_record = self.fiscal_year_id
        fiscal_start_year = fiscal_year_record.date_from.year
        fiscal_end_year = fiscal_year_record.date_to.year

        return {
            "oct": (fiscal_start_year, 10),
            "nov": (fiscal_start_year, 11),
            "dec": (fiscal_start_year, 12),
            "jan": (fiscal_end_year, 1),
            "feb": (fiscal_end_year, 2),
            "mar": (fiscal_end_year, 3),
            "apr": (fiscal_end_year, 4),
            "may": (fiscal_end_year, 5),
            "jun": (fiscal_end_year, 6),
            "jul": (fiscal_end_year, 7),
            "aug": (fiscal_end_year, 8),
            "sep": (fiscal_end_year, 9),
        }

    def _get_budget_data_values(self, record_type, field_name):
        "Generic method to get values from budget.data for different record types and fields"
        _logger.info(
            "Starting _get_budget_data_values for hotel: %s, Record Type: %s, Field: %s",
            self.hotel,
            record_type,
            field_name,
        )

        monthly_values = {month: 0 for month in MONTHLY_FIELDS}

        if not self.hotel or not self.fiscal_year_id:
            _logger.info("Missing hotel or fiscal_year_id - returning zeros")
            return monthly_values

        # Get fiscal-month mapping for the fiscal year
        month_mapping = self._get_fiscal_month_mapping()
        _logger.info("Month mapping: %s", month_mapping)

        # Search in budget.data using year/month
        for fiscal_month, (calendar_year, calendar_month) in month_mapping.items():
            budget_data_records = self.env["budget.data"].search(
                [
                    ("pms_property_id", "=", self.hotel.id),
                    ("year", "=", str(calendar_year)),
                    ("month", "=", str(calendar_month)),
                ]
            )

            _logger.info(
                "Searching for %s/%02d - Found %s records",
                calendar_year,
                calendar_month,
                len(budget_data_records),
            )

            for budget_data in budget_data_records:
                current_value = getattr(budget_data, field_name, 0) or 0
                monthly_values[fiscal_month] = current_value
                _logger.info(
                    "Mapped %s/%02d to fiscal month %s: %s",
                    calendar_year,
                    calendar_month,
                    fiscal_month,
                    current_value,
                )

        _logger.info("Final monthly values: %s", monthly_values)
        return monthly_values

    def _get_rooms_available_from_budget_data(self, department_prefix=""):
        "Get rooms available from budget.data for the current fiscal year and hotel."
        monthly_values = {month: 0 for month in MONTHLY_FIELDS}

        log_prefix = department_prefix or f"[{self._name.upper()}]"

        if not (self.hotel and self.fiscal_year_id):
            _logger.warning(
                "%s Skipping sync - Missing hotel (%s) or fiscal year (%s)",
                log_prefix,
                self.hotel,
                self.fiscal_year_id,
            )
            return monthly_values

        _logger.info("%s Searching budget.data for hotel %s", log_prefix, self.hotel.id)

        all_budget_data = self.env["budget.data"].search(
            [("pms_property_id", "=", self.hotel.id)]
        )
        _logger.info(
            "%s Found %s budget.data records", log_prefix, len(all_budget_data)
        )

        try:
            month_year_mapping = self._get_fiscal_month_mapping()

            if not month_year_mapping:
                _logger.info("%s No fiscal mapping available", log_prefix)
                return monthly_values

            _logger.info("%s Processing 12 months for fiscal mapping", log_prefix)
            for month_field, (
                calendar_year,
                calendar_month,
            ) in month_year_mapping.items():
                _logger.info(
                    "%s Processing %s: %s/%02d",
                    log_prefix,
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
                    "%s Found %s budget.data records for %s/%s",
                    log_prefix,
                    len(budget_data),
                    calendar_year,
                    calendar_month,
                )

                if budget_data and budget_data.total_rooms_available:
                    monthly_values[month_field] = budget_data.total_rooms_available
                    _logger.info(
                        "%s STORED: %s = %s",
                        log_prefix,
                        month_field,
                        budget_data.total_rooms_available,
                    )

        except Exception as e:
            _logger.error(
                "%s EXCEPTION in _get_rooms_available_from_budget_data: %s",
                log_prefix,
                e,
            )

        _logger.info("%s RETURNING monthly_values: %s", log_prefix, monthly_values)
        return monthly_values

    def _get_previous_fiscal_year(self, current_fiscal_year):
        "Get the previous fiscal year based on the current fiscal year"
        if not current_fiscal_year:
            return None

        # Calculate previous year based on fiscal year start date
        current_start_date = current_fiscal_year.date_from
        previous_year = current_start_date.year - 1

        # Search for fiscal year that starts in the previous year
        previous_fiscal_year = self.env["account.fiscal.year"].search(
            [
                ("date_from", ">=", f"{previous_year}-01-01"),
                ("date_from", "<", f"{previous_year + 1}-01-01"),
            ],
            limit=1,
        )

        if previous_fiscal_year:
            _logger.info(
                "Found previous fiscal year: %s for current fiscal year: %s",
                previous_fiscal_year.name,
                current_fiscal_year.name,
            )
        else:
            _logger.warning(
                "No previous fiscal year found: %s (looking for year %s)",
                current_fiscal_year.name,
                previous_year,
            )

        return previous_fiscal_year
