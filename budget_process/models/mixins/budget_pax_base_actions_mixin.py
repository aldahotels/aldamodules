# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetPaxBaseActionsMixin(models.AbstractModel):
    """Base mixin for pax budgeted actions that can be used by any department"""

    _name = "budget.pax.base.actions.mixin"
    _description = "Budget Pax Base Actions Mixin"

    def action_diagnose_pax_budgeted_formula_base(self, department_prefix=""):
        """Base diagnostic method to show how the pax budgeted formula is applied"""
        dept_name = department_prefix.strip("[]") if department_prefix else "Budget"

        message = []
        message.append(f"🔍 {dept_name.upper()} PAX BUDGETED FORMULA DIAGNOSIS: \n\n")

        records_processed = 0
        for record in self:
            if not record._is_pax_budgeted():
                continue

            if not (record.fiscal_year_id and record.hotel):
                continue

            records_processed += 1

            previous_fiscal_year = record._get_previous_fiscal_year(
                record.fiscal_year_id
            )

            message.append(f"🏨 HOTEL: {record.hotel.name}\n")
            message.append(f"📅 Current Fiscal Year: {record.fiscal_year_id.name}\n")
            message.append(
                f"📅 Previous Fiscal Year: "
                f"{previous_fiscal_year.name if previous_fiscal_year else 'NOT FOUND'}\n"
            )
            message.append(
                "\n🧮 FORMULA: pax_budgeted * (1 + increase_decrease_rn_ly)\n"
            )

            if previous_fiscal_year:
                previous_year_record = self.env["budget.revenue"].search(
                    [
                        ("hotel", "=", record.hotel.id),
                        ("fiscal_year_id", "=", previous_fiscal_year.id),
                        ("record_type", "=", "increase_decrease_rn_ly"),
                        ("budget_type", "=", "budgeted"),
                    ],
                    limit=1,
                )

                if previous_year_record:
                    if (
                        hasattr(previous_year_record, "percentage_increase_decrease")
                        and previous_year_record.percentage_increase_decrease
                    ):
                        rate_percentage = (
                            previous_year_record.percentage_increase_decrease
                        )
                        rate_decimal = rate_percentage / 100.0
                        message.append(
                            f"✅ Found increase_decrease_rn_ly: "
                            f"{rate_percentage}% (decimal: {rate_decimal})\n"
                        )
                    else:
                        monthly_sum = sum(
                            getattr(previous_year_record, month, 0)
                            for month in MONTHLY_FIELDS
                        )
                        rate_percentage = monthly_sum / 12.0
                        rate_decimal = rate_percentage / 100.0
                        message.append(
                            f"✅ Calculated average rate: "
                            f"{rate_percentage}% (decimal: {rate_decimal})\n"
                        )

                    message.append("\n📊 EXAMPLE CALCULATIONS:\n")
                    month_year_mapping = record._get_fiscal_month_mapping()

                    count = 0
                    for month_field, (
                        calendar_year,
                        calendar_month,
                    ) in month_year_mapping.items():
                        if count >= 3:
                            break

                        budget_data = self.env["budget.data"].search(
                            [
                                ("pms_property_id", "=", record.hotel.id),
                                ("year", "=", str(calendar_year)),
                                ("month", "=", str(calendar_month)),
                            ],
                            limit=1,
                        )

                        if budget_data and budget_data.total_pax:
                            base_pax = budget_data.total_pax
                            adjusted_pax = base_pax * (1 + rate_decimal)
                            current_value = getattr(record, month_field, 0)

                            message.append(
                                f"• {month_field.upper()}: {base_pax} * "
                                f"(1 + {rate_decimal}) = {adjusted_pax: .2f} "
                                f"Current: {current_value}\n"
                            )
                        count += 1

                else:
                    message.append(
                        "❌ NO increase_decrease_rn_ly record found for "
                        "previous fiscal year\n"
                    )
                    message.append("💡 Create a budget.revenue record with: \n")
                    message.append(f" - Hotel: {record.hotel.name}\n")
                    message.append(f" - Fiscal Year: {previous_fiscal_year.name}\n")
                    message.append(" - Record Type: increase_decrease_rn_ly\n")
                    message.append(" - Budget Type: budgeted\n")
            else:
                message.append("❌ Previous fiscal year not found\n")
                message.append("💡 The formula will use rate = 0% (no adjustment)\n")

            message.append("=" * 60 + "\n")

        if records_processed == 0:
            message.append("⚠️ No PAX budgeted records found to diagnose.\n")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"{dept_name} PAX Budgeted Formula Diagnosis",
                "message": "".join(message),
                "type": "info",
                "sticky": True,
            },
        }
