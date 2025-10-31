# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class BudgetRoomsBaseActionsMixin(models.AbstractModel):
    "Base mixin for rooms available actions that can be used by any department"
    _name = "budget.rooms.base.actions.mixin"
    _description = "Budget Rooms Base Actions Mixin"

    def action_refresh_rooms_available_base(self, department_prefix=""):
        "Refresh rooms available method"
        updated_count = 0
        dept_name = department_prefix.strip("[]") if department_prefix else "Budget"

        for record in self:
            if record._is_rooms_available_budgeted():
                if not (record.fiscal_year_id and record.hotel):
                    _logger.warning(
                        "%s Record %s missing fiscal_year_id or hotel, skipping sync",
                        department_prefix,
                        record.id,
                    )
                    continue

                monthly_values = record._get_rooms_available_from_budget_data(
                    department_prefix
                )
                record.write(monthly_values)
                updated_count += 1

                _logger.info(
                    "%s Refreshed rooms available for %s fiscal %s",
                    department_prefix,
                    record.hotel.name,
                    record.fiscal_year_id.name,
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"{dept_name} - Rooms Available Refreshed",
                "message": (
                    f"Updated {updated_count} {dept_name} records with correct "
                    "fiscal year mapping from budget.data"
                ),
                "type": "success",
                "sticky": True,
            },
        }

    def action_diagnose_current_records_base(self, department_prefix=""):
        "Diagnostic for any department"

        dept_name = department_prefix.strip("[]") if department_prefix else "Budget"
        problems = []

        for record in self:
            if record._is_rooms_available_budgeted():
                if not record.fiscal_year_id:
                    problems.append(
                        f"{dept_name} Record {record.id}: Falta fiscal_year_id"
                    )
                elif not record.hotel:
                    problems.append(f"{dept_name} Record {record.id}: Falta hotel")
                elif record.hotel:
                    data_count = self.env["budget.data"].search_count(
                        [("pms_property_id", "=", record.hotel.id)]
                    )
                    if not data_count:
                        problems.append(
                            f"{dept_name} Record {record.id} "
                            f"({record.hotel.name}): No budget.data"
                        )
        message = []
        if problems:
            message.append(f"⚠️ {dept_name.upper()} PROBLEMS FOUND: \n ")
            message.extend(problems)
            message.append("\n")
            message.append("💡 Use 'Fix Sync Problems' to automatically correct ")
        else:
            message.append(f"✅ All {dept_name} records are configured correctly ")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"🔍 {dept_name} Quick Diagnosis",
                "message": message,
                "type": "warning" if problems else "success",
            },
        }

    def action_show_sync_status_base(self, department_prefix=""):
        "Sync status display for any department"
        dept_name = department_prefix.strip("[]") if department_prefix else "Budget"

        for record in self:
            if record._is_rooms_available_budgeted():
                if not record.fiscal_year_id:
                    continue

                message = [
                    f"📊 {dept_name.upper()} SYNC STATUS - {record.hotel.name} "
                    f"(Fiscal Year {record.fiscal_year_id.name}): \n\n"
                    "FULL SYNCHRONIZATION CHECK: "
                ]

                all_budget_data = self.env["budget.data"].search(
                    [("pms_property_id", "=", record.hotel.id)]
                )

                message.append(
                    f"\n📋 Total record in budget.data for "
                    f"{record.hotel.name}: {len(all_budget_data)}"
                )

                if not all_budget_data:
                    message.append(
                        "\n❌ PROBLEM: No records in budget.data for this hotel"
                    )
                    message.append(
                        "\n💡 SOLUTION: Create records in budget.data or load from pms.budget"
                    )
                else:
                    sample_data = all_budget_data[:5]
                    message.append("\n\n📝 Examples of available data:")
                    for data in sample_data:
                        message.append(
                            f"\n• {data.year}/{data.month.zfill(2)}: "
                            f"{data.total_rooms_available} rooms"
                        )

                # Use the auxiliary fiscal mapping
                month_year_mapping = record._get_fiscal_month_mapping()
                fiscal_start_year = record.fiscal_year_id.date_from.year

                message.append(
                    f"\n\n🗓️ MAPEO FISCAL YEAR {fiscal_start_year} "
                    f"(Oct {fiscal_start_year} - Sep {fiscal_start_year + 1}): "
                )

                found_data = []
                missing_data = []

                for month_field, (
                    calendar_year,
                    calendar_month,
                ) in month_year_mapping.items():
                    # Search in budget.data
                    budget_data = self.env["budget.data"].search(
                        [
                            ("pms_property_id", "=", record.hotel.id),
                            ("year", "=", str(calendar_year)),
                            ("month", "=", str(calendar_month)),
                        ],
                        limit=1,
                    )

                    current_value = getattr(record, month_field, 0)

                    if budget_data:
                        status = (
                            "✅"
                            if current_value == budget_data.total_rooms_available
                            else "⚠️"
                        )
                        found_data.append(
                            f"{status} {month_field.upper()}: "
                            f"{calendar_year}/{calendar_month: 02d} "
                            f"Budget: {budget_data.total_rooms_available}, "
                            f"{dept_name}: {current_value}"
                        )
                    else:
                        missing_data.append(
                            f"❌ {month_field.upper()}: "
                            f"{calendar_year}/{calendar_month: 02d} "
                            "NO DATA in budget.data"
                        )

                if found_data:
                    message.append("\n\n✅ Data Found:")
                    for data in found_data:
                        message.append(f"\n{data}")

                if missing_data:
                    message.append("\n\n❌ Missing Data:")
                    for data in missing_data:
                        message.append(f"\n{data}")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"{dept_name} Sync Status - {record.hotel.name}",
                "message": message,
                "type": "info",
                "sticky": True,
            },
        }

    def action_fix_sync_problems_base(self, department_prefix=""):
        "Fix sync problems for any department"

        dept_name = department_prefix.strip("[]") if department_prefix else "Budget"
        fixes_applied = []
        errors_found = []

        for record in self:
            if record._is_rooms_available_budgeted():
                if not record.fiscal_year_id:
                    if record.hotel:
                        available_data = self.env["budget.data"].search(
                            [("pms_property_id", "=", record.hotel.id)]
                        )

                        if available_data:
                            available_years = [
                                int(data.year) for data in available_data
                            ]
                            latest_year = max(available_years)

                            fiscal_year = self.env["account.fiscal.year"].search(
                                [
                                    ("date_from", "<=", f"{latest_year}-12-31"),
                                    ("date_to", ">=", f"{latest_year}-01-01"),
                                ],
                                limit=1,
                            )

                            if fiscal_year:
                                try:
                                    record.write({"fiscal_year_id": fiscal_year.id})
                                    fixes_applied.append(
                                        f"{dept_name} Record {record.id} "
                                        f"({record.hotel.name}): "
                                        f"fiscal_year_id None '{fiscal_year.name}'"
                                    )
                                except Exception as e:
                                    errors_found.append(
                                        f"{dept_name} Record {record.id}: "
                                        f"Error setting fiscal_year_id - {e}"
                                    )

        message = [
            f"🔧 {dept_name.upper()} FIXES APPLIED: \n\n✅ "
            f"FIXES APPLIED ({len(fixes_applied)}): \n"
        ]
        for fix in fixes_applied:
            message.append(f"\n• {fix}")

        if errors_found:
            message.append(f"\n\n❌ ERRORS FOUND ({len(errors_found)}): ")
            for error in errors_found:
                message.append(f"\n• {error}")

        message.append(
            "\n\n💡 RECOMMENDATION: Monthly fields will be automatically "
            "updated when changing fiscal_year_id."
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"🔧 {dept_name} Automatic Correction Completed",
                "message": "\n".join(message),
                "type": "success" if fixes_applied else "warning",
                "sticky": True,
            },
        }

    def action_sync_all_rooms_available_base(
        self, department_prefix="", additional_record_types=None
    ):
        "Sync all rooms available method for any department"
        dept_name = department_prefix.strip("[]") if department_prefix else "Budget"

        # Build domain for record types
        record_types = ["rooms_available"]
        if additional_record_types:
            record_types.extend(additional_record_types)

        domain = [("record_type", "in", record_types)]
        records = self.search(domain)

        if not records:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": f"Sin Registros {dept_name}",
                    "message": (
                        f'No se encontraron registros de {dept_name} tipo "Rooms Available" '
                        "para sincronizar."
                    ),
                    "type": "warning",
                },
            }

        updated_count = 0
        for record in records:
            if record._is_rooms_available_budgeted():
                monthly_values = record._get_rooms_available_from_budget_data(
                    department_prefix
                )
                record.write(monthly_values)
                updated_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"✅ {dept_name} Sync Completed",
                "message": (
                    f'{updated_count} "rooms available" records '
                    "were synchronized with fiscal year data"
                ),
                "type": "success",
            },
        }
