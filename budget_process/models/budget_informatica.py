# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

months = [
    "oct",
    "nov",
    "dec",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
]

_logger = logging.getLogger(__name__)


class BudgetInformatica(models.Model):
    _name = "budget.informatica"
    _description = "IT budget"
    _inherit = "budget.base"

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
            "Amount to be used for calculations: Per Room (×rooms), "
            "Distributed (÷12), Rooms Available (×synced rooms per month)"
        ),
    )

    # Automatic monthly fields that should be computed automatically
    oct = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    nov = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    dec = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    jan = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    feb = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    mar = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    apr = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    may = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    jun = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    jul = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    aug = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)
    sep = fields.Float(compute="_compute_monthly_amounts", store=True, readonly=False)

    # Auxiliary methods
    def _is_rooms_available_budgeted(self):
        """Check if it's a budgeted rooms available record for sync"""
        return self.record_type == "rooms_available" and self.budget_type == "budgeted"

    def _get_fiscal_month_mapping(self):
        """Returns a mapping of fiscal months to (calendar_year, calendar_month)"""
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

    @api.depends(
        "record_type", "budget_type", "hotel", "fiscal_year_id", "manual_amount"
    )
    def _compute_monthly_amounts(self):
        """Compute monthly amounts based on record_type and budget_type"""
        for record in self:
            monthly_values = {month: 0 for month in months}

            # Logic 1: Rooms Available × Manual Amount (NEW CALCULATION)
            if record._is_rooms_available_budgeted():
                if record.manual_amount:
                    # Get rooms available from budget.data
                    rooms_available_data = (
                        record._get_rooms_available_from_budget_data()
                    )
                    # Multiply each month's rooms by manual_amount
                    for month in months:
                        rooms_count = rooms_available_data.get(month, 0)
                        monthly_values[month] = rooms_count * record.manual_amount
                    _logger.info(
                        "[IT] Calculated monthly amounts: rooms_available × %s = %s",
                        record.manual_amount,
                        monthly_values,
                    )
                else:
                    # If no manual_amount, just sync rooms available (original behavior)
                    monthly_values = record._get_rooms_available_from_budget_data()
                    _logger.info(
                        "[IT] No manual_amount, showing raw rooms available: %s",
                        monthly_values,
                    )

            # Logic 3: Distributed amount
            elif record.record_type == "distributed" and record.manual_amount:
                monthly_amount = record.manual_amount / 12.0
                monthly_values = {month: monthly_amount for month in months}

            # Apply values to fields
            for month in months:
                setattr(record, month, monthly_values[month])

    def _get_current_year_rooms_count(self):
        """Get current number of rooms for calculations"""
        if not self.hotel:
            return 0

        try:
            # Try to get from PMS first
            PmsRoom = self.env.get("pms.room")
            if PmsRoom:
                rooms = PmsRoom.search([("property_id", "=", self.hotel.id)])
                return len(rooms)

            # Fallback: try to get from budget.data
            budget_data = self.env["budget.data"].search(
                [("pms_property_id", "=", self.hotel.id)], limit=1
            )

            if budget_data and budget_data.total_rooms_available:
                return budget_data.total_rooms_available

            return 0
        except Exception as e:
            _logger.warning(f"Error getting room count: {e}")
            return 0

    def _get_rooms_available_from_budget_data(self):
        """Get rooms available from budget.data (IT version)"""
        monthly_values = {month: 0 for month in months}

        if not (self.hotel and self.fiscal_year_id):
            _logger.warning(
                "[IT] Skipping sync - Missing hotel (%s) or fiscal year (%s)",
                self.hotel,
                self.fiscal_year_id,
            )
            return monthly_values

        _logger.info("[IT] Searching budget.data for hotel %s", self.hotel.id)

        all_budget_data = self.env["budget.data"].search(
            [("pms_property_id", "=", self.hotel.id)]
        )
        _logger.info("[IT] Found %s budget.data records", len(all_budget_data))

        try:
            month_year_mapping = self._get_fiscal_month_mapping()

            if not month_year_mapping:
                _logger.info("[IT] No fiscal mapping available")
                return monthly_values

            _logger.info("[IT] Processing 12 months for fiscal mapping")
            for month_field, (
                calendar_year,
                calendar_month,
            ) in month_year_mapping.items():
                _logger.info(
                    "[IT] Processing %s: %s/%02d",
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
                    "[IT] Found %s budget.data records for %s/%s",
                    len(budget_data),
                    calendar_year,
                    calendar_month,
                )
                if budget_data and budget_data.total_rooms_available:
                    monthly_values[month_field] = budget_data.total_rooms_available
                    _logger.info(
                        "[IT] STORED: %s = %s",
                        month_field,
                        budget_data.total_rooms_available,
                    )

        except Exception as e:
            _logger.error(
                "[IT] EXCEPTION in _get_rooms_available_from_budget_data: %s", e
            )

        _logger.info("[IT] RETURNING monthly_values: %s", monthly_values)
        return monthly_values

    def action_refresh_rooms_available(self):
        """Refresh rooms available from budget.data (IT version)"""
        updated_count = 0

        for record in self:
            if record._is_rooms_available_budgeted():
                if not (record.fiscal_year_id and record.hotel):
                    _logger.warning(
                        "[IT] Record %s missing fiscal_year_id or hotel, skipping sync",
                        record.id,
                    )
                    continue

                monthly_values = record._get_rooms_available_from_budget_data()
                record.write(monthly_values)
                updated_count += 1

                _logger.info(
                    "[IT] Refreshed rooms available for %s fiscal %s",
                    record.hotel.name,
                    record.fiscal_year_id.name,
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "IT - Rooms Available Refreshed",
                "message": (
                    f"Updated {updated_count} IT records with correct "
                    "fiscal year mapping from budget.data"
                ),
                "type": "success",
                "sticky": True,
            },
        }

    def action_sync_all_rooms_available(self):
        """Synchronization of all IT records with rooms available type"""
        domain = [("record_type", "=", "rooms_available")]
        it_records = self.search(domain)

        if not it_records:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Sin Registros IT",
                    "message": (
                        'No se encontraron registros de IT tipo "Rooms Available" '
                        "para sincronizar."
                    ),
                    "type": "warning",
                },
            }  # Synchronization process
        updated_count = 0
        for record in it_records:
            if record._is_rooms_available_budgeted():
                monthly_values = record._get_rooms_available_from_budget_data()
                record.write(monthly_values)
                updated_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "✅ IT Sync Completed",
                "message": (
                    f'{updated_count} "rooms available" records '
                    "were synchronized with fiscal year data"
                ),
                "type": "success",
            },
        }

    def action_show_sync_status(self):
        """
        Show detailed sync status and diagnostics for rooms available
        """
        for record in self:
            if record._is_rooms_available_budgeted():
                if not record.fiscal_year_id:
                    continue

                message = (
                    f"📊 SYNC STATUS - {record.hotel.name} "
                    f"(Fiscal Year {record.fiscal_year_id.name}): \n\n"
                    "FULL SYNCHRONIZATION CHECK: "
                )
                # Check if there are any budget.data records for this hotel
                all_budget_data = self.env["budget.data"].search(
                    [("pms_property_id", "=", record.hotel.id)]
                )

                message += (
                    f"\n📋 Total record in budget.data for {record.hotel.name}: "
                    f"{len(all_budget_data)}"
                )

                if not all_budget_data:
                    message += "\n❌ PROBLEM: No records in budget.data for this hotel"
                    message += (
                        "\n💡 SOLUTION: Create records in budget.data "
                        "or load from pms.budget"
                    )
                else:
                    # Show some sample data examples
                    sample_data = all_budget_data[:5]
                    message += "\n\n📝 Examples of available data:"
                    for data in sample_data:
                        message += (
                            f"\n• {data.year}/{data.month.zfill(2)}: "
                            f"{data.total_rooms_available} rooms"
                        )

                # Use the auxiliary fiscal mapping
                month_year_mapping = record._get_fiscal_month_mapping()
                fiscal_start_year = record.fiscal_year_id.date_from.year

                message += (
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
                            f"{calendar_year}/{calendar_month: 02d} → "
                            f"Budget: {budget_data.total_rooms_available}, "
                            f"Revenue: {current_value}"
                        )
                    else:
                        missing_data.append(
                            f"❌ {month_field.upper()}: "
                            f"{calendar_year}/{calendar_month: 02d} → "
                            "NO DATA in budget.data"
                        )

                if found_data:
                    message += "\n\n✅ Data Found:"
                    for data in found_data:
                        message += f"\n{data}"

                if missing_data:
                    message += "\n\n❌ Missing Data:"
                    for data in missing_data:
                        message += f"\n{data}"

                # User-specific example for fiscal year
                if fiscal_start_year == 2024:
                    message += "\n\n🎯 USER-SPECIFIC EXAMPLE:"
                    message += (
                        "\nIf in budget.data Sept 2025 you have 10 rooms → "
                        "it must appear in revenue fiscal 2024 field 'sep'"
                    )

                    sept_data = self.env["budget.data"].search(
                        [
                            ("pms_property_id", "=", record.hotel.id),
                            ("year", "=", "2025"),
                            ("month", "=", "9"),
                        ],
                        limit=1,
                    )

                    if sept_data:
                        message += (
                            f"\n• Budget.Data Sept 2025: "
                            f"{sept_data.total_rooms_available} rooms"
                        )
                        message += f"\n• Revenue Sep (fiscal 2024): {record.sep} rooms"
                        if record.sep == sept_data.total_rooms_available:
                            message += "\n• ✅ CORRECT SYNCHRONIZATION"
                        else:
                            message += (
                                "\n• ⚠️ OUT OF SYNC - " "Use 'Refresh Rooms Available'"
                            )
                    else:
                        message += "\n• ❌ No data in budget.data for September 2025"
                        message += "\n• 💡 Create record in budget.data for Sept 2025"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"Sync Status - {record.hotel.name}",
                "message": message,
                "type": "info",
                "sticky": True,
            },
        }

    def action_diagnose_current_records(self):
        """
        Diagnostic to identify sync problems in rooms available budgeted records:
        """
        problems = []

        for record in self:
            if record._is_rooms_available_budgeted():
                if not record.fiscal_year_id:
                    problems.append(f"Record {record.id}: Falta fiscal_year_id")

                elif not record.hotel:
                    problems.append(f"Record {record.id}: Falta hotel")

                elif record.hotel:
                    data_count = self.env["budget.data"].search_count(
                        [("pms_property_id", "=", record.hotel.id)]
                    )
                    if not data_count:
                        problems.append(
                            f"Record {record.id} ({record.hotel.name}): No budget.data"
                        )

        if problems:
            message = "⚠️ PROBLEM FOUND:\n" + "\n".join(problems)
            message += "\n\n💡 Use 'Fix Sync Problems' to automatically correct"
        else:
            message = "✅ All records are configured correctly"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "🔍 Quick Diagnosis",
                "message": message,
                "type": "warning" if problems else "success",
            },
        }

    def action_fix_sync_problems(self):
        """
        Fix sync problems in rooms available budgeted records.
        """
        fixes_applied = []
        errors_found = []

        for record in self:
            if record._is_rooms_available_budgeted():

                # FIX 1: fiscal year missing
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
                                        f"Record {record.id} ({record.hotel.name}): "
                                        f"fiscal_year_id None → '{fiscal_year.name}'"
                                    )
                                except Exception as e:
                                    errors_found.append(
                                        f"Record {record.id}: "
                                        f"Error setting fiscal_year_id - {e}"
                                    )
                            else:
                                errors_found.append(
                                    f"Record {record.id}: "
                                    f"No fiscal year found for data year {latest_year}"
                                )
                        else:
                            errors_found.append(
                                f"Record {record.id} ({record.hotel.name}): "
                                "No budget.data available to suggest fiscal year"
                            )
                    else:
                        errors_found.append(f"Record {record.id}: No hotel assigned")

                # FIX 2: check if hotel has budget.data
                elif record.hotel and record.fiscal_year_id:
                    fixes_applied.append(
                        f"Record {record.id}: Ready for auto-sync "
                        f"with fiscal year {record.fiscal_year_id.name}"
                    )

        # Final summary message
        message = """🔧 FIXES APPLIED:

        ✅ FIXES APPLIED (%s):
        """ % len(
            fixes_applied
        )
        for fix in fixes_applied:
            message += f"\n• {fix}"

        if errors_found:
            message += f"\n\n❌ ERRORS FOUND ({len(errors_found)}): "
            for error in errors_found:
                message += f"\n• {error}"

        message += (
            "\n\n💡 RECOMMENDATION: Monthly fields will be automatically "
            "updated when changing fiscal_year_id."
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "🔧 Automatic Correction Completed",
                "message": message,
                "type": "success" if fixes_applied else "warning",
                "sticky": True,
            },
        }
