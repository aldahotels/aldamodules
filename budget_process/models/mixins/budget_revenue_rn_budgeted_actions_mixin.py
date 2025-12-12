# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetRevenueRnBudgetedActionsMixin(models.AbstractModel):
    "Mixin for RN Budgeted specific actions and debugging"
    _name = "budget.revenue.rn.budgeted.actions.mixin"
    _description = "Budget Revenue RN Budgeted Actions Mixin"

    def action_check_rn_budgeted_dependencies(self):
        "Check if all required records exist for RN Budgeted calculation"
        for record in self:
            if record._is_rn_budgeted():
                if not (record.hotel and record.fiscal_year_id and record.budget_type):
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Missing Configuration",
                            "message": (
                                "RN Budgeted requires:"
                                " hotel, fiscal_year_id and budget_type to be set"
                            ),
                            "type": "warning",
                            "sticky": True,
                        },
                    }

                current_fiscal_year = record.fiscal_year_id
                previous_fiscal_year = record._get_previous_fiscal_year(
                    current_fiscal_year
                )

                message = []
                message.append("🔍 RN BUDGETED DEPENDENCIES CHECK\n\n")
                message.append(f"• Hotel: {record.hotel.name}\n")
                message.append(f"• Current Fiscal Year: {current_fiscal_year.name}\n")
                message.append(
                    f"• Previous Fiscal Year: "
                    f"{previous_fiscal_year.name if previous_fiscal_year else 'NOT FOUND'}\n"
                )
                message.append(f"• Budget Type: {record.budget_type} ✅\n")
                message.append("─" * 50 + "\n")

                if not previous_fiscal_year:
                    message.append("❌ ERROR: No previous fiscal year found!\n")
                    message.append(
                        f"💡 Create a fiscal year before {current_fiscal_year.name}\n"
                    )
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Missing Previous Fiscal Year",
                            "message": message,
                            "type": "error",
                            "sticky": True,
                        },
                    }

                previous_year_domain = [
                    ("hotel", "=", record.hotel.id),
                    ("fiscal_year_id", "=", previous_fiscal_year.id),
                    ("budget_type", "=", "budgeted"),
                ]

                same_year_domain = [
                    ("hotel", "=", record.hotel.id),
                    ("fiscal_year_id", "=", current_fiscal_year.id),
                    ("budget_type", "=", "budgeted"),
                ]

                rn_ly_record = self.env["budget.revenue"].search(
                    previous_year_domain + [("record_type", "=", "rn_ly")], limit=1
                )
                increase_decrease_record = self.env["budget.revenue"].search(
                    previous_year_domain
                    + [("record_type", "=", "increase_decrease_rn_ly")],
                    limit=1,
                )
                rooms_available_record = self.env["budget.revenue"].search(
                    same_year_domain + [("record_type", "=", "rooms_available")],
                    limit=1,
                )

                status_ok = True

                if rn_ly_record:
                    message.append(
                        f"• RN LY record found in {previous_fiscal_year.name} ✅\n"
                    )
                else:
                    message.append(
                        f"• RN LY record MISSING in {previous_fiscal_year.name} ❌\n"
                    )
                    status_ok = False

                if increase_decrease_record:
                    message.append(
                        f"• Increase/Decrease RN LY record found in "
                        f"{previous_fiscal_year.name} ✅\n"
                    )
                else:
                    message.append(
                        f"• Increase/Decrease RN LY record MISSING in "
                        f"{previous_fiscal_year.name} ❌\n"
                    )
                    status_ok = False

                if rooms_available_record:
                    message.append(
                        f"• Rooms Available record found in {current_fiscal_year.name} ✅\n"
                    )
                else:
                    message.append(
                        f"• Rooms Available record MISSING in {current_fiscal_year.name} ❌\n"
                    )
                    status_ok = False

                message.append("─" * 50 + "\n")

                if status_ok:
                    message.append("🎯 All dependencies are available!\n\n")
                    message.append("Formula:\n")
                    formula = (
                        f"min(rn_ly_{previous_fiscal_year.name} × "
                        f"(1 + increase_decrease_rn_ly_{previous_fiscal_year.name}%), "
                        f"rooms_available_{current_fiscal_year.name})"
                    )
                    message.append(formula + "\n")
                    message_type = "success"
                else:
                    message.append("💡 SOLUTION STEPS:\n")
                    step_number = 1
                    if not rn_ly_record:
                        message.append(
                            f"{step_number}. Create RN LY (budgeted) record for "
                            f"{record.hotel.name} "
                            f"in fiscal year {previous_fiscal_year.name}\n"
                        )
                        step_number += 1
                    if not increase_decrease_record:
                        message.append(
                            f"{step_number}. Create Increase/Decrease RN LY record for "
                            f"{record.hotel.name} in fiscal year {previous_fiscal_year.name}\n"
                        )
                        step_number += 1
                    if not rooms_available_record:
                        message.append(
                            f"{step_number}. Create Rooms Available (budgeted) record for "
                            f"{record.hotel.name} in fiscal year {current_fiscal_year.name}\n"
                        )
                    message_type = "warning"

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "RN Budgeted Dependencies",
                        "message": "\n".join(message),
                        "type": message_type,
                        "sticky": True,
                    },
                }

    def action_debug_rn_budgeted(self):
        """Debug method to investigate why RN Budgeted formula is not working."""
        for record in self:
            if record.record_type == "rn_budgeted":
                debug_lines = []
                debug_lines.append(f"🔍 Debug RN Budgeted - Record ID: {record.id}\n")
                debug_lines.append("📋 Basic Conditions:")
                debug_lines.append(f"• Record Type: {record.record_type}")
                debug_lines.append(f"• Budget Type: {record.budget_type}")
                debug_lines.append(
                    f"• Hotel: {record.hotel.name if record.hotel else 'NOT SET'}"
                )
                debug_lines.append(
                    f"• Fiscal Year: "
                    f"{record.fiscal_year_id.name if record.fiscal_year_id else 'NOT SET'}"
                )
                debug_lines.append(f"• _is_rn_budgeted(): {record._is_rn_budgeted()}")
                debug_lines.append("─" * 40)

                if not record._is_rn_budgeted():
                    debug_lines.append("❌ Problem: _is_rn_budgeted() returns False")
                    debug_lines.append(
                        "• Expected: record_type='rn_budgeted' AND budget_type='budgeted'"
                    )
                    debug_lines.append(
                        f"• Actual: record_type='{record.record_type}' "
                        f"AND budget_type='{record.budget_type}'"
                    )

                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Debug RN Budgeted - Basic Check Failed",
                            "message": "\n".join(debug_lines),
                            "type": "error",
                            "sticky": True,
                        },
                    }

                debug_lines.append("🧮 Manual Formula Test:")
                try:
                    monthly_values = record._get_rn_budgeted_values()
                    debug_lines.append(f"• Formula result: {monthly_values}")
                    debug_lines.append(
                        f"• Sample calculation for Oct: {monthly_values.get('oct', 'N/A')}"
                    )
                except Exception as e:
                    debug_lines.append(f"• Formula ERROR: {str(e)}")

                debug_lines.append("─" * 40)

                debug_lines.append("📊 Current Field Values:")
                current_values = {
                    month: getattr(record, month, 0) for month in MONTHLY_FIELDS
                }
                debug_lines.append(f"• Current monthly values: {current_values}")

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Debug RN Budgeted - Complete Analysis",
                        "message": "\n".join(debug_lines),
                        "type": "info",
                        "sticky": True,
                    },
                }

    def action_force_recalculate_rn_budgeted(self):
        updated_count = 0

        for record in self:
            if record.record_type == "rn_budgeted":
                _logger.info("Force recalculation: Starting for record %s", record.id)

                old_values = {
                    month: getattr(record, month, 0) for month in MONTHLY_FIELDS
                }

                record._compute_monthly_amounts()

                new_values = {
                    month: getattr(record, month, 0) for month in MONTHLY_FIELDS
                }

                changed = old_values != new_values
                if changed:
                    updated_count += 1

                _logger.info(
                    "FORCE RECALC: Record %s - Changed: %s, Old: %s, New: %s",
                    record.id,
                    changed,
                    old_values,
                    new_values,
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Force Recalculation Complete",
                "message": f"Processed {len(self)} records, {updated_count} were updated",
                "type": "success",
                "sticky": True,
            },
        }
