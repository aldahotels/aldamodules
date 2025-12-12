# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

from .budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetInformatica(models.Model):
    _name = "budget.informatica"
    _description = "IT budget"
    _inherit = [
        "budget.base",
        "budget.calculation.mixin",
        "budget.it.actions.mixin",
    ]

    department = fields.Selection(
        [("informatica", "Informática")],
        default="informatica",
        readonly=True,
    )

    # Field to differentiate record type
    record_type = fields.Selection(
        [
            ("distributed", "Distributed Amount"),
            ("rooms_available", "Rooms Available"),
        ],
        required=True,
        default="rooms_available",
        help=(
            " Distributed: Divide total amount across 12 months."
            " Rooms Available: Sync rooms from budget.data, then multiply by amount"
        ),
    )

    # field for budget amount
    manual_amount = fields.Float(
        help=(
            "Amount to be used for calculations: Per Room (rooms), "
            "Distributed (÷12), Rooms Available (synced rooms per month)"
        ),
    )

    def _is_rooms_available_budgeted(self):
        """Check if it's a budgeted rooms available record for sync."""
        return self.record_type == "rooms_available" and self.budget_type == "budgeted"

    @api.depends(
        "record_type", "budget_type", "hotel", "fiscal_year_id", "manual_amount"
    )
    def _compute_monthly_amounts(self):
        "Compute monthly amounts based on record_type and budget_type"
        for record in self:
            monthly_values = {month: 0 for month in MONTHLY_FIELDS}

            # Rooms Available × Manual Amount
            if record._is_rooms_available_budgeted():
                if record.manual_amount:
                    # Get rooms available from budget.data using unified method
                    rooms_available_data = record._get_rooms_available_from_budget_data(
                        "[IT]"
                    )
                    # Multiply each month's rooms by manual_amount
                    for month in MONTHLY_FIELDS:
                        rooms_count = rooms_available_data.get(month, 0)
                        monthly_values[month] = rooms_count * record.manual_amount
                    _logger.info(
                        "[IT] Calculated monthly amounts: rooms_available × %s = %s",
                        record.manual_amount,
                        monthly_values,
                    )
                else:
                    # If no manual_amount, just sync rooms available
                    monthly_values = record._get_rooms_available_from_budget_data(
                        "[IT]"
                    )
                    _logger.info(
                        "[IT] No manual_amount, showing raw rooms available: %s",
                        monthly_values,
                    )

            # Distributed amount
            elif record.record_type == "distributed" and record.manual_amount:
                monthly_amount = record.manual_amount / 12.0
                monthly_values = {month: monthly_amount for month in MONTHLY_FIELDS}

            # Apply values to fields
            for month in MONTHLY_FIELDS:
                setattr(record, month, monthly_values[month])
