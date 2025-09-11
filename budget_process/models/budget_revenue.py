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


class BudgetRevenue(models.Model):
    _name = "budget.revenue"
    _description = "Revenue budget"
    _inherit = "budget.base"

    department = fields.Selection(
        [("revenue", "Revenue")], default="revenue", readonly=True
    )

    record_type = fields.Selection(
        [
            ("rooms_available_ly", "Rooms Available LY"),
            ("rooms_available", "Rooms Available"),
            ("rn_ly", "RN LY"),
            ("aumento_disminucion_rn_ly", "Aumento o Disminución RN / LY"),
            ("rn_presupuestadas", "RN Presupuestadas"),
            ("occ_presupuestada", "Occ Presupuestada"),
            ("pax_presupuestadas", "Pax Presupuestadas"),
            ("room_revenue_ly_sin_iva", "Room Revenue LY (SIN IVA)"),
            ("adr_ly_sin_iva", "ADR LY (SIN IVA)"),
            ("aumento_disminucion_adr_ly", "Aumento o Disminución ADR / LY"),
            ("adr_sin_iva", "ADR (SIN IVA)"),
            ("70500000000", "Habitaciones (4)"),
            (
                "aumento_disminucion_otros_servicios_ly",
                "Aumento o Disminución Otros Servicios / LY",
            ),
            ("70500000030", "Parking (3)"),
            ("70500000031", "Lavandería (3)"),
            ("70500000032", "Coworking (3)"),
            ("70500000034", "Otros ingresos Hotel (4)"),
            ("70500000035", "Otros ingresos Spa (4)"),
            ("70500000036", "Otros ingresos Restaurante (4)"),
            ("70500000037", "Otros ingresos Bar (4)"),
            ("70900000000", "Rappels sobre ventas (4)"),
            ("62900000040", "Comisión de reservas (4)"),
            ("77800000001", "% Ingresos / total revenue (4)"),
            ("77800000000", "Ingresos excepcionales (4)"),
        ],
        required=True,
        default="rooms_available",
        help="Each record type represents a different KPI calculated monthly from PMS",
    )

    # Automatic monthly fields that should be computed automatically
    oct = fields.Float(compute="_compute_monthly_amounts", store=True)
    nov = fields.Float(compute="_compute_monthly_amounts", store=True)
    dec = fields.Float(compute="_compute_monthly_amounts", store=True)
    jan = fields.Float(compute="_compute_monthly_amounts", store=True)
    feb = fields.Float(compute="_compute_monthly_amounts", store=True)
    mar = fields.Float(compute="_compute_monthly_amounts", store=True)
    apr = fields.Float(compute="_compute_monthly_amounts", store=True)
    may = fields.Float(compute="_compute_monthly_amounts", store=True)
    jun = fields.Float(compute="_compute_monthly_amounts", store=True)
    jul = fields.Float(compute="_compute_monthly_amounts", store=True)
    aug = fields.Float(compute="_compute_monthly_amounts", store=True)
    sep = fields.Float(compute="_compute_monthly_amounts", store=True)

    # Auxiliary methods
    def _is_rooms_available_budgeted(self):
        return self.record_type == "rooms_available" and self.budget_type == "budgeted"

    def _get_fiscal_month_mapping(self):
        """
        Returns a mapping of fiscal months to (calendar_year, calendar_month)
        """
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

    @api.depends("record_type", "budget_type", "hotel", "fiscal_year_id")
    def _compute_monthly_amounts(self):
        """
        Compute monthly amounts based on record_type and budget_type
        """
        for record in self:
            monthly_values = {month: 0 for month in months}

            # Only for rooms_available budgeted obtain data from budget.data
            if record._is_rooms_available_budgeted():
                monthly_values = record._get_rooms_available_from_budget_data()

            for month in months:
                setattr(record, month, monthly_values[month])

    def _get_rooms_available_from_budget_data(self):
        """
        Improved method to get rooms available from budget.data
        """

        # Initialize monthly values
        monthly_values = {month: 0 for month in months}

        # Preliminary validation: Must have hotel and fiscal year
        if not (self.hotel and self.fiscal_year_id):
            _logger.warning(
                "Skipping sync - Missing hotel (%s) or fiscal year (%s)",
                self.hotel,
                self.fiscal_year_id,
            )
            return monthly_values

        # Check if there are any budget.data records for this hotel
        all_budget_data = self.env["budget.data"].search(
            [("pms_property_id", "=", self.hotel.id)]
        )
        _logger.info(f"[REVENUE] >>>> Found {len(all_budget_data)} budget.data records")

        try:
            # Use the auxiliary fiscal mapping function
            month_year_mapping = self._get_fiscal_month_mapping()

            if not month_year_mapping:
                return monthly_values

            for month_field, (
                calendar_year,
                calendar_month,
            ) in month_year_mapping.items():

                budget_data = self.env["budget.data"].search(
                    [
                        ("pms_property_id", "=", self.hotel.id),
                        ("year", "=", str(calendar_year)),
                        ("month", "=", str(calendar_month)),
                    ],
                    limit=1,
                )

                if budget_data:
                    if budget_data.total_rooms_available:
                        monthly_values[month_field] = budget_data.total_rooms_available
                        _logger.info(
                            "[REVENUE] >>>>> STORED: %s = %s",
                            month_field,
                            budget_data.total_rooms_available,
                        )
                        _logger.info(
                            "✅ FISCAL SYNC %s: " "%s fiscal %s ← %s/%02d = %s",
                            month_field,
                            self.hotel.name,
                            self.fiscal_year_id.name,
                            calendar_year,
                            calendar_month,
                            budget_data.total_rooms_available,
                        )
                    else:
                        _logger.info(
                            "[REVENUE] >>>>> SKIPPED: total_rooms_available is 0/NULL"
                        )
                else:
                    _logger.info(
                        "[REVENUE] >>>>> NO DATA: No budget.data found for %s/%s",
                        calendar_year,
                        calendar_month,
                    )

        except Exception as e:
            _logger.error(
                f"[REVENUE] >>>> EXCEPTION in _get_rooms_available_from_budget_data: {e}"
            )
            _logger.error(f"Error in fiscal sync for {self.hotel.name}: {e}")

        _logger.info(f"[REVENUE] >>>> RETURNING monthly_values: {monthly_values}")
        return monthly_values

    def action_refresh_rooms_available(self):
        """
        Refresh rooms available from budget.data with improved fiscal logic
        """
        updated_count = 0

        for record in self:

            if record._is_rooms_available_budgeted():
                if not (record.fiscal_year_id and record.hotel):
                    _logger.warning(
                        "Record %s missing fiscal_year_id or hotel, skipping sync",
                        record.id,
                    )
                    continue

                monthly_values = record._get_rooms_available_from_budget_data()
                record.write(monthly_values)
                updated_count += 1

                _logger.info(
                    "Refreshed rooms available for %s fiscal %s: "
                    "Oct=%s, Nov=%s, Dec=%s, Jan=%s, Feb=%s, Mar=%s, "
                    "Apr=%s, May=%s, Jun=%s, Jul=%s, Aug=%s, Sep=%s",
                    record.hotel.name,
                    record.fiscal_year_id.name,
                    monthly_values["oct"],
                    monthly_values["nov"],
                    monthly_values["dec"],
                    monthly_values["jan"],
                    monthly_values["feb"],
                    monthly_values["mar"],
                    monthly_values["apr"],
                    monthly_values["may"],
                    monthly_values["jun"],
                    monthly_values["jul"],
                    monthly_values["aug"],
                    monthly_values["sep"],
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Rooms Available Refreshed (Improved)",
                "message": (
                    "Updated %s records with correct fiscal "
                    "year mapping from budget.data" % updated_count
                ),
                "type": "success",
                "sticky": True,
            },
        }

    def action_sync_all_rooms_available(self):
        """
        Synchronization of all available rooms.
        """
        domain = [("record_type", "=", "rooms_available")]
        revenue_records = self.search(domain)

        if not revenue_records:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Sin Registros",
                    "message": 'No records of type "Rooms Available" were found to synchronize',
                    "type": "warning",
                },
            }

        # Syncronization process
        for record in revenue_records:
            record._sync_rooms_available_from_fiscal_year()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "✅ Sincronización Completada",
                "message": (
                    "Se sincronizaron %s registros de rooms available "
                    "con los datos del año fiscal." % len(revenue_records)
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
                    "📊 SYNC STATUS - %s (Fiscal Year %s):\n\n FULL SYNCHRONIZATION CHECK: "
                    % (
                        record.hotel.name,
                        record.fiscal_year_id.name,
                    )
                )
                # Check if there are any budget.data records for this hotel
                all_budget_data = self.env["budget.data"].search(
                    [("pms_property_id", "=", record.hotel.id)]
                )

                message += "\n📋 Total record in budget.data for %s: %s" % (
                    record.hotel.name,
                    len(all_budget_data),
                )

                if not all_budget_data:
                    message += (
                        "\n❌ PROBLEM: No records in " "budget.data for this hotel"
                    )
                    message += (
                        "\n💡 SOLUTION: Create records in "
                        "budget.data or load from pms.budget"
                    )
                else:
                    # Show some sample data examples
                    sample_data = all_budget_data[:5]
                    message += "\n\n📝 Examples of available data:"
                    for data in sample_data:
                        message += "\n• %s/%s: %s rooms" % (
                            data.year,
                            data.month.zfill(2),
                            data.total_rooms_available,
                        )

                # Use the auxiliary fiscal mapping
                month_year_mapping = record._get_fiscal_month_mapping()
                fiscal_start_year = record.fiscal_year_id.date_from.year

                message += "\n\n🗓️ MAPEO FISCAL YEAR %s (Oct %s - Sep %s):" % (
                    fiscal_start_year,
                    fiscal_start_year,
                    fiscal_start_year + 1,
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
                            "%s %s: %s/%02d → Budget: %s, Revenue: %s"
                            % (
                                status,
                                month_field.upper(),
                                calendar_year,
                                calendar_month,
                                budget_data.total_rooms_available,
                                current_value,
                            )
                        )
                    else:
                        missing_data.append(
                            "❌ %s: %s/%02d → NO DATA in budget.data"
                            % (
                                month_field.upper(),
                                calendar_year,
                                calendar_month,
                            )
                        )

                if found_data:
                    message += "\n\n✅ Data Found:"
                    for data in found_data:
                        message += "\n%s" % data

                if missing_data:
                    message += "\n\n❌ Missing Data:"
                    for data in missing_data:
                        message += "\n%s" % data

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
                            "\n• Budget.Data Sept 2025: %s rooms"
                            % sept_data.total_rooms_available
                        )
                        message += (
                            "\n• Revenue Sep (fiscal 2024): %s rooms" % record.sep
                        )
                        if record.sep == sept_data.total_rooms_available:
                            message += "\n• ✅ CORRECT SYNCHRONIZATION"
                        else:
                            message += (
                                "\n• ⚠️ OUT OF SYNC - Use 'Refresh Rooms Available'"
                            )
                    else:
                        message += "\n• ❌ No data in budget.data for September 2025"
                        message += "\n• 💡 Create record in budget.data for Sept 2025"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sync Status - %s" % record.hotel.name,
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
                    problems.append("Record %s: Falta fiscal_year_id" % record.id)

                elif not record.hotel:
                    problems.append("Record %s: Falta hotel" % record.id)

                elif record.hotel:
                    data_count = self.env["budget.data"].search_count(
                        [("pms_property_id", "=", record.hotel.id)]
                    )
                    if not data_count:
                        problems.append(
                            "Record %s (%s): No budget.data"
                            % (record.id, record.hotel.name)
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
                                        "Record %s (%s): fiscal_year_id None → '%s'"
                                        % (
                                            record.id,
                                            record.hotel.name,
                                            fiscal_year.name,
                                        )
                                    )
                                except Exception as e:
                                    errors_found.append(
                                        "Record %s: Error setting fiscal_year_id - %s"
                                        % (record.id, e)
                                    )
                            else:
                                errors_found.append(
                                    "Record %s: No fiscal year found for data year %s"
                                    % (record.id, latest_year)
                                )
                        else:
                            errors_found.append(
                                (
                                    "Record %s (%s): No budget.data"
                                    " available to suggest fiscal year"
                                )
                                % (
                                    record.id,
                                    record.hotel.name,
                                )
                            )
                    else:
                        errors_found.append("Record %s: No hotel assigned" % record.id)

                # FIX 2: check if hotel has budget.data
                elif record.hotel and record.fiscal_year_id:
                    fixes_applied.append(
                        "Record %s: Ready for auto-sync with fiscal year %s"
                        % (
                            record.id,
                            record.fiscal_year_id.name,
                        )
                    )

        # Final summary message
        message = "🔧 FIXES APPLIED:\n\n       " "✅ FIXES APPLIED (%s):\n        " % len(
            fixes_applied
        )
        for fix in fixes_applied:
            message += "\n• %s" % fix

        if errors_found:
            message += "\n\n❌ ERRORS FOUND (%s):" % len(errors_found)
            for error in errors_found:
                message += "\n• %s" % error

        message += (
            "\n\n💡 RECOMMENDATION: Monthly fields will be "
            "automatically updated when changing fiscal_year_id."
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
