# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


import logging
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BudgetData(models.Model):
    _name = "budget.data"
    _description = "Budget Data - PMS Integration"
    _order = "year desc, month desc, pms_property_id"

    # Basic identification fields
    pms_property_id = fields.Many2one(
        "pms.property", string="Property", required=True, help="PMS Property"
    )
    month = fields.Selection(
        [
            ("1", "January"),
            ("2", "February"),
            ("3", "March"),
            ("4", "April"),
            ("5", "May"),
            ("6", "June"),
            ("7", "July"),
            ("8", "August"),
            ("9", "September"),
            ("10", "October"),
            ("11", "November"),
            ("12", "December"),
        ],
        required=True,
    )

    year = fields.Char(required=True, size=4)

    # Fields from pms.budget DataBI
    room_nights = fields.Float(
        string="Room Nights (Budget)",
        digits=(6, 2),
        help="Room Nights from pms.budget DataBI",
    )
    room_revenue = fields.Float(
        string="Room Revenue (Budget)",
        digits=(6, 2),
        help="Room Revenue from pms.budget DataBI",
    )

    # New fields for real PMS data
    room_nights_real = fields.Float(
        string="Room Nights (Real)",
        compute="_compute_real_data_from_pms",
        store=True,
        digits=(6, 2),
        help="Real Room Nights from PMS reservations",
    )

    room_revenue_real = fields.Float(
        string="Room Revenue (Real)",
        compute="_compute_real_data_from_pms",
        store=True,
        digits=(6, 2),
        help="Real Room Revenue from PMS reservations",
    )

    blocked_rooms = fields.Float(
        compute="_compute_real_data_from_pms",
        store=True,
        digits=(6, 2),
        help="Blocked rooms from PMS",
    )

    # Field for total rooms available in the month
    total_rooms_available = fields.Integer(
        compute="_compute_total_rooms_available",
        store=True,
        help="Total rooms available",
    )

    # Field for total pax in the month
    total_pax = fields.Integer(
        compute="_compute_real_data_from_pms",
        store=True,
        help="Total guests (pax) from PMS reservations",
    )

    def _get_excluded_room_type_ids(self):
        "Get list of excluded room type IDs"
        return [103, 79, 80, 81, 28, 9, 102, 82, 83, 86, 87, 84, 85, 21, 99, 96]

    @api.depends("pms_property_id", "year", "month")
    def _compute_total_rooms_available(self):
        "Calculate total rooms available"
        for record in self:
            if not (record.pms_property_id and record.year and record.month):
                record.total_rooms_available = 0
                continue

            try:
                year_int = int(record.year)
                month_int = int(record.month)
                first_day = date(year_int, month_int, 1)
                if month_int == 12:
                    last_day = date(year_int + 1, 1, 1) - timedelta(days=1)
                else:
                    last_day = date(year_int, month_int + 1, 1) - timedelta(days=1)

                # Get excluded room type IDs
                excluded_room_type_ids = record._get_excluded_room_type_ids()

                # Count total rooms
                total_rooms = self.env["pms.room"].search_count(
                    [
                        ("pms_property_id", "=", record.pms_property_id.id),
                        ("room_type_id", "not in", excluded_room_type_ids),
                        ("active", "=", True),
                        ("room_type_id.overnight_room", "=", True),
                    ]
                )

                # Calculate days in month
                days_in_month = (last_day - first_day).days + 1

                # Total rooms available = total_rooms * days_in_month
                record.total_rooms_available = total_rooms * days_in_month

                _logger.info(
                    "Calculated total_rooms_available for %s %s/%s: %s rooms × %s days = %s",
                    record.pms_property_id.name,
                    record.year,
                    record.month,
                    total_rooms,
                    days_in_month,
                    record.total_rooms_available,
                )
            except (ValueError, TypeError) as e:
                _logger.warning(
                    "Error calculating total_rooms_available for %s %s/%s: %s",
                    record.pms_property_id.name,
                    record.year,
                    record.month,
                    e,
                )
                record.total_rooms_available = 0

    @api.depends("pms_property_id", "year", "month")
    def _compute_real_data_from_pms(self):
        "Compute real data from PMS"
        for record in self:
            if not (record.pms_property_id and record.year and record.month):
                record.room_nights_real = 0
                record.room_revenue_real = 0
                record.blocked_rooms = 0
                record.total_pax = 0
                continue

            try:
                year_int = int(record.year)
                month_int = int(record.month)
                first_day = date(year_int, month_int, 1)
                if month_int == 12:
                    last_day = date(year_int + 1, 1, 1) - timedelta(days=1)
                else:
                    last_day = date(year_int, month_int + 1, 1) - timedelta(days=1)

                excluded_room_type_ids = record._get_excluded_room_type_ids()

                # Get filtered reservation lines
                reservation_lines = self.env["pms.reservation.line"].search(
                    [
                        ("date", ">=", first_day),
                        ("date", "<=", last_day),
                        ("pms_property_id", "=", record.pms_property_id.id),
                        ("room_id.room_type_id", "not in", excluded_room_type_ids),
                        ("room_id.room_type_id.overnight_room", "=", True),
                        ("room_id.active", "=", True),
                        "|",
                        "&",
                        ("reservation_id.reservation_type", "=", "normal"),
                        ("state", "not in", ["draft", "cancel"]),
                        "&",
                        ("reservation_id.reservation_type", "=", "out"),
                        ("state", "not in", ["draft", "cancel"]),
                    ]
                )

                # Initialize counters
                total_pax = 0
                total_revenue = 0
                room_nights = 0
                blocked_rooms = 0

                # Process each reservation line
                for line in reservation_lines:
                    reservation = line.reservation_id

                    if reservation.reservation_type == "normal":
                        # Count PAX (adults + children)
                        total_pax += (reservation.adults or 0) + (
                            reservation.children or 0
                        )
                        # Sum revenue
                        total_revenue += line.price_day_total or 0
                        # Count room nights
                        room_nights += 1
                    elif reservation.reservation_type == "out":
                        # Count blocked rooms
                        blocked_rooms += 1

                # Assign computed values
                record.total_pax = total_pax
                record.room_revenue_real = total_revenue
                record.room_nights_real = room_nights
                record.blocked_rooms = blocked_rooms

                _logger.info(
                    "Calculated real PMS data for %s %s/%s: "
                    "PAX=%s, Revenue=%s, RN=%s, Blocked=%s (from %s reservation lines)",
                    record.pms_property_id.name,
                    record.year,
                    record.month,
                    record.total_pax,
                    record.room_revenue_real,
                    record.room_nights_real,
                    record.blocked_rooms,
                    len(reservation_lines),
                )

            except (ValueError, TypeError) as e:
                _logger.warning(
                    "Error calculating real PMS data for %s %s/%s: %s",
                    record.pms_property_id.name,
                    record.year,
                    record.month,
                    e,
                )
                record.total_pax = 0
                record.room_revenue_real = 0
                record.room_nights_real = 0
                record.blocked_rooms = 0

    def action_diagnose_availability(self):
        "Diagnostic of availability and guests"
        for record in self:
            if not (record.pms_property_id and record.year and record.month):
                continue
            try:
                year_int = int(record.year)
                month_int = int(record.month)
                first_day = date(year_int, month_int, 1)
                if month_int == 12:
                    last_day = date(year_int + 1, 1, 1) - timedelta(days=1)
                else:
                    last_day = date(year_int, month_int + 1, 1) - timedelta(days=1)

                availabilities = self.env["pms.availability"].search(
                    [
                        ("date", ">=", first_day),
                        ("date", "<=", last_day),
                        ("pms_property_id", "=", record.pms_property_id.id),
                    ]
                )

                # Room types in the property
                room_types = self.env["pms.room.type"].search(
                    [
                        ("room_ids.pms_property_id", "=", record.pms_property_id.id),
                        ("room_ids.active", "=", True),
                    ]
                )

                # Guests (PAX) for days in the month
                reservation_lines = self.env["pms.reservation.line"].search(
                    [
                        ("date", ">=", first_day),
                        ("date", "<=", last_day),
                        ("occupies_availability", "=", True),
                    ]
                )

                pax_by_day = {}
                for line in reservation_lines:
                    reservation = line.reservation_id
                    if (
                        reservation
                        and reservation.pms_property_id.id == record.pms_property_id.id
                        and reservation.state not in ("cancel", "draft")
                    ):
                        pax_by_day.setdefault(line.date, 0)
                        pax_by_day[line.date] += (
                            reservation.adults + reservation.children
                        )

                message = (
                    f"AVAILABILITY & PAX DIAGNOSIS - "
                    f"{record.pms_property_id.name} {record.year}/{record.month}: \n"
                    f"📅 Period: {first_day} to {last_day}\n"
                    f"📊 Availability records found: {len(availabilities)}\n"
                    f"👥 Reservation lines found: {len(reservation_lines)}\n"
                    f"🏨 Room types in property: "
                    f"{len(room_types)} ({', '.join(room_types.mapped('name'))})\n"
                    f"🛏️ Total rooms per room type: "
                    f"{sum(room_types.mapped('total_rooms_count'))}\n"
                    "📋 AVAILABILITY detail by day:"
                )

                for avail in availabilities.sorted("date"):
                    message += (
                        f"\n  {avail.date} - {avail.room_type_id.name}: "
                        f"{avail.real_avail} rooms"
                    )

                if not availabilities:
                    message += "\n⚠️  No availability records found for this period"

                message += "\n\n📋 PAX detail by day:"
                for day in sorted(pax_by_day.keys()):
                    message += f"\n  {day}: {pax_by_day[day]} pax"

                if not pax_by_day:
                    message += "\n⚠️  No reservation lines found for this period"

                total_rooms = sum(availabilities.mapped("real_avail"))
                total_pax = sum(pax_by_day.values())
                message += "\n\n✅ CALCULATED TOTALS:"
                message += f"\n   🛏️ Available rooms: {total_rooms}"
                message += f"\n   👥 Total pax: {total_pax}"

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Availability Diagnosis",
                        "message": message,
                        "type": "info",
                        "sticky": True,
                    },
                }
            except Exception as e:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Diagnosis Error",
                        "message": f"Error: {str(e)}",
                        "type": "danger",
                    },
                }

    def action_load_from_budget(self):
        "Load data from pms.budget DataBI"
        for record in self:
            if record.pms_property_id and record.year and record.month:
                # Search for record in pms.budget
                pms_budget = self.env["pms.budget"].search(
                    [
                        ("pms_property_id", "=", record.pms_property_id.id),
                        ("year", "=", record.year),
                        ("month", "=", record.month),
                    ],
                    limit=1,
                )

                if pms_budget:
                    # Load exact data from DataBI
                    record.write(
                        {
                            "room_nights": pms_budget.room_nights,
                            "room_revenue": pms_budget.room_revenue,
                        }
                    )

                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Budget Data Loaded",
                            "message": (
                                f"Loaded from pms.budget: "
                                f"RN={pms_budget.room_nights}, "
                                f"Revenue={pms_budget.room_revenue}"
                            ),
                            "type": "success",
                        },
                    }
                else:
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "No Budget Found",
                            "message": (
                                f"No pms.budget found for "
                                f"{record.pms_property_id.name} "
                                f"{record.year}/{record.month}"
                            ),
                            "type": "warning",
                        },
                    }

    def action_load_all_from_budget(self):
        "Load all records from pms.budget DataBI"
        # Get all records from pms.budget
        pms_budgets = self.env["pms.budget"].search([])

        created_count = 0
        updated_count = 0

        for budget in pms_budgets:
            # Search for existing record
            existing = self.search(
                [
                    ("pms_property_id", "=", budget.pms_property_id.id),
                    ("year", "=", budget.year),
                    ("month", "=", budget.month),
                ]
            )

            if existing:
                # Update existing record
                existing.write(
                    {
                        "room_nights": budget.room_nights,
                        "room_revenue": budget.room_revenue,
                    }
                )
                updated_count += 1
            else:
                # Create new record
                self.create(
                    {
                        "pms_property_id": budget.pms_property_id.id,
                        "year": budget.year,
                        "month": budget.month,
                        "room_nights": budget.room_nights,
                        "room_revenue": budget.room_revenue,
                    }
                )
                created_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Bulk Budget Load Complete",
                "message": (
                    f"Created {created_count} new records, "
                    f"Updated {updated_count} existing records "
                    "from pms.budget DataBI."
                ),
                "type": "success",
                "sticky": True,
            },
        }

    def action_load_from_pms_real_data(self):
        "Load real data from PMS using ORM (replaces DataBI dependency)"
        for record in self:
            if record.pms_property_id and record.year and record.month:
                # Trigger recomputation of real data
                record._compute_real_data_from_pms()
                record._compute_total_rooms_available()

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Real PMS Data Loaded",
                        "message": (
                            f"Loaded from PMS: "
                            f"RN={record.room_nights_real}, "
                            f"Revenue={record.room_revenue_real}, "
                            f"PAX={record.total_pax}, "
                            f"Blocked={record.blocked_rooms}, "
                            f"Available={record.total_rooms_available}"
                        ),
                        "type": "success",
                    },
                }

    def action_load_all_real_data(self):
        "Load real PMS data for all records"
        records = self.search([])
        processed_count = 0

        for record in records:
            if record.pms_property_id and record.year and record.month:
                # Trigger recomputation
                record._compute_real_data_from_pms()
                record._compute_total_rooms_available()
                processed_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Bulk Real Data Load Complete",
                "message": f"Processed {processed_count} records with real PMS data.",
                "type": "success",
                "sticky": True,
            },
        }
