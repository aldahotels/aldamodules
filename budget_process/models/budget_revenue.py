# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


import logging
from datetime import date

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BudgetRevenue(models.Model):
    _name = "budget.revenue"
    _description = "Revenue budget"
    _inherit = "budget.base"

    department = fields.Selection(
        [("revenue", "Revenue")], default="revenue", readonly=True
    )

    # Campo para diferenciar el tipo de registro
    record_type = fields.Selection(
        [
            ("pms_data", "PMS Data (KPIs)"),
            ("account_budget", "Accounting Budget"),
        ],
        required=True,
        default="pms_data",
        help="PMS Data: Operational KPIs from PMS system./"
        "Accounting Budget: Financial budget by account",
    )

    # Campos base para calculos
    # Factores de crecimiento
    rn_growth_factor = fields.Float(
        string="RN Growth Factor (%)",
        default=2.0,
        help="Percentage of growth for Room Nights",
    )
    adr_growth_factor = fields.Float(
        string="ADR Growth Factor (%)",
        default=2.0,
        help="Percentage of growth for ADR",
    )
    services_growth_factor = fields.Float(
        string="Services Growth Factor (%)",
        default=2.0,
        help="Percentage of growth for other services",
    )

    # Datos históricos (obtenidos automáticamente desde PMS)
    rooms_available_ly = fields.Float(
        string="Rooms Available LY",
        compute="_compute_historical_data",
        store=True,
        help="Available rooms last year (from PMS)",
    )
    room_nights_ly = fields.Float(
        string="Room Nights LY",
        compute="_compute_historical_data",
        store=True,
        help="Nights sold last year (from PMS)",
    )
    room_revenue_ly = fields.Float(
        string="Room Revenue LY",
        compute="_compute_historical_data",
        store=True,
        help="Room revenue last year (from PMS)",
    )
    pax_ly = fields.Float(
        string="PAX LY",
        compute="_compute_historical_data",
        store=True,
        help="Guests last year (from PMS)",
    )

    # Datos del año actual
    rooms_available_current = fields.Float(
        string="Rooms Available Current Year",
        compute="_compute_current_year_data",
        store=True,
        help="Available rooms current year (from PMS)",
    )

    # Campos calculados

    # Rooms disponibles
    """rooms_available = fields.Float(
        string="Rooms Available",
        compute="_compute_rooms_available",
        store=True,
        help="Available rooms current year",
    )"""

    # Room Nights presupuestadas
    room_nights_budget = fields.Float(
        string="Room Nights",
        compute="_compute_room_nights_budget",
        store=True,
        help="Nights sold budgeted",
    )

    # Ocupación presupuestada
    occupancy_budget = fields.Float(
        string="Occupancy (%)",
        compute="_compute_occupancy_budget",
        store=True,
        help="Percentage of occupancy budgeted",
    )

    # ADR año pasado
    adr_ly = fields.Float(
        string="ADR LY",
        compute="_compute_adr_ly",
        store=True,
        help="Average Daily Rate last year",
    )

    # ADR presupuestado
    adr_budget = fields.Float(
        string="ADR",
        compute="_compute_adr_budget",
        store=True,
        help="Average Daily Rate presupuestado",
    )

    # PAX presupuestadas
    pax_budget = fields.Float(
        string="PAX Budget",
        compute="_compute_pax_budget",
        store=True,
        help="Guests budgeted",
    )

    # Room Revenue presupuestad
    room_revenue_budget = fields.Float(
        string="Room Revenue",
        compute="_compute_room_revenue_budget",
        store=True,
        help="Room revenue budgeted",
    )

    # Metodos de calculo
    @api.depends("hotel", "year", "record_type")
    def _compute_historical_data(self):
        for record in self:
            if record.record_type != "pms_data":
                record.update(
                    {
                        "rooms_available_ly": 0.0,
                        "room_nights_ly": 0.0,
                        "room_revenue_ly": 0.0,
                        "pax_ly": 0.0,
                    }
                )
                continue

            if not record.hotel or not record.year:
                record.update(
                    {
                        "rooms_available_ly": 0.0,
                        "room_nights_ly": 0.0,
                        "room_revenue_ly": 0.0,
                        "pax_ly": 0.0,
                    }
                )
                continue

            try:
                last_year = int(record.year) - 1

                first_day = date(last_year, 10, 1)
                last_day = date(int(record.year), 9, 30)

                date_from = first_day.strftime("%Y-%m-%d")
                date_to = last_day.strftime("%Y-%m-%d")

                # Obtener datos del PMS
                if self.env["ir.model"].search([("model", "=", "pms.reservation")]):
                    pms_data = record._get_pms_reservation_data(
                        record.hotel.id, date_from, date_to
                    )
                    record.update(
                        {
                            "rooms_available_ly": pms_data["rooms_available"],
                            "room_nights_ly": pms_data["room_nights"],
                            "room_revenue_ly": pms_data["room_revenue"],
                            "pax_ly": pms_data["pax"],
                        }
                    )
                else:
                    revenue = record._get_accounting_revenue_data(
                        record.hotel.id, date_from, date_to
                    )
                    record.update(
                        {
                            "rooms_available_ly": 0.0,
                            "room_nights_ly": 0.0,
                            "room_revenue_ly": revenue,
                            "pax_ly": 0.0,
                        }
                    )
            except Exception:
                record.update(
                    {
                        "rooms_available_ly": 0.0,
                        "room_nights_ly": 0.0,
                        "room_revenue_ly": 0.0,
                        "pax_ly": 0.0,
                    }
                )

    @api.depends("hotel", "year", "record_type")
    def _compute_current_year_data(self):
        """
        Calcula automáticamente los datos del año actual desde PMS
        Solo para registros de tipo 'pms_data'
        """
        for record in self:
            if record.record_type != "pms_data":
                record.rooms_available_current = 0.0
                continue

            if not record.hotel:
                record.rooms_available_current = 0.0
                continue

            try:
                current_rooms = record._get_current_year_rooms_from_pms(
                    record.hotel.id, record.year
                )
                record.rooms_available_current = current_rooms
            except Exception:
                record.rooms_available_current = 0.0

    @api.depends(
        "room_nights_ly", "rn_growth_factor", "rooms_available_current", "record_type"
    )
    # Calcula las noches de habitación presupuestadas
    def _compute_room_nights_budget(self):
        for record in self:
            if record.record_type != "pms_data":
                record.room_nights_budget = 0.0
                continue
            if record.room_nights_ly and record.rooms_available_current:
                projected_rn = record.room_nights_ly * (
                    1 + record.rn_growth_factor / 100
                )
                record.room_nights_budget = min(
                    projected_rn, record.rooms_available_current
                )
            else:
                record.room_nights_budget = 0.0

    @api.depends("room_nights_budget", "rooms_available_current", "record_type")
    # Calcula la ocupación presupuestada
    def _compute_occupancy_budget(self):
        for record in self:
            if record.record_type != "pms_data":
                record.occupancy_budget = 0.0
                continue
            if record.rooms_available_current and record.rooms_available_current > 0:
                occupancy = record.room_nights_budget / record.rooms_available_current
                record.occupancy_budget = min(occupancy * 100, 100.0)
            else:
                record.occupancy_budget = 0.0

    @api.depends("room_revenue_ly", "room_nights_ly", "record_type")
    # Calcula el ADR del año pasado
    def _compute_adr_ly(self):
        for record in self:
            if record.record_type != "pms_data":
                record.adr_ly = 0.0
                continue
            if record.room_nights_ly and record.room_nights_ly > 0:
                record.adr_ly = record.room_revenue_ly / record.room_nights_ly
            else:
                record.adr_ly = 0.0

    @api.depends("adr_ly", "adr_growth_factor", "record_type")
    # Calcula el ADR presupuestado
    def _compute_adr_budget(self):
        for record in self:
            if record.record_type != "pms_data":
                record.adr_budget = 0.0
                continue
            record.adr_budget = record.adr_ly * (1 + record.adr_growth_factor / 100)

    @api.depends("pax_ly", "rn_growth_factor", "record_type")
    # Calcula el presupuesto de Pax
    def _compute_pax_budget(self):
        for record in self:
            if record.record_type != "pms_data":
                record.pax_budget = 0.0
                continue
            record.pax_budget = record.pax_ly * (1 + record.rn_growth_factor / 100)

    @api.depends("room_nights_budget", "adr_budget", "record_type")
    # Calcula el Room Revenue presupuestado
    def _compute_room_revenue_budget(self):
        for record in self:
            if record.record_type != "pms_data":
                record.room_revenue_budget = 0.0
                continue
            record.room_revenue_budget = record.room_nights_budget * record.adr_budget

    # Metodos para integracion con el pms
    def get_historical_data_from_pms(self):
        for record in self:
            if not record.hotel:
                continue

            try:
                last_year = int(record.year) - 1
                first_day = date(last_year, 10, 1)
                last_day = date(int(record.year), 9, 30)

                date_from = first_day.strftime("%Y-%m-%d")
                date_to = last_day.strftime("%Y-%m-%d")

                if self.env["ir.model"].search([("model", "=", "pms.reservation")]):
                    reservation_data = self._get_pms_reservation_data(
                        record.hotel.id, date_from, date_to
                    )

                    record.write(
                        {
                            "rooms_available_ly": reservation_data["rooms_available"],
                            "room_nights_ly": reservation_data["room_nights"],
                            "room_revenue_ly": reservation_data["room_revenue"],
                            "pax_ly": reservation_data["pax"],
                        }
                    )

                    current_rooms = self._get_current_year_rooms_from_pms(
                        record.hotel.id, record.year
                    )
                    if current_rooms:
                        record.rooms_available_current = current_rooms

                else:
                    revenue_data = self._get_accounting_revenue_data(
                        record.hotel.id, date_from, date_to
                    )
                    record.room_revenue_ly = revenue_data

            except Exception as e:
                _logger.warning(
                    f"Error obteniendo datos del PMS para {record.year}-{record.month}: {e}"
                )

    # Obtiene los datos de reservas del pms para un hotel
    def _get_pms_reservation_data(self, property_id, date_from, date_to):
        PmsReservation = self.env.get("pms.reservation")
        if not PmsReservation:
            return {
                "rooms_available": 0,
                "room_nights": 0,
                "room_revenue": 0,
                "pax": 0,
            }

        domain = [
            ("property_id", "=", property_id),
            ("checkin", ">=", date_from),
            ("checkout", "<=", date_to),
            ("state", "!=", "cancelled"),
        ]

        reservations = PmsReservation.search(domain)

        # Calcular métricas
        room_nights = sum(reservation.nights for reservation in reservations)
        room_revenue = sum(
            reservation.amount_room
            for reservation in reservations
            if hasattr(reservation, "amount_room")
        )
        pax = sum(
            reservation.adults + reservation.children for reservation in reservations
        )

        # Obtener habitaciones disponibles del año pasado
        rooms_available = self._get_rooms_available_from_pms(property_id, date_from)

        return {
            "rooms_available": rooms_available,
            "room_nights": room_nights,
            "room_revenue": room_revenue,
            "pax": pax,
        }

    # Obtiene el numero de habitaciones disponibles desde el pms
    def _get_rooms_available_from_pms(self, property_id, date):
        PmsRoom = self.env.get("pms.room")
        if not PmsRoom:
            return 0

        rooms = PmsRoom.search(
            [
                ("property_id", "=", property_id),
            ]
        )

        return len(rooms)

    # Obtiene el numero de habitaciones disponibles del pms para un año especifico
    def _get_current_year_rooms_from_pms(self, property_id, year=None):
        if year:
            year_int = int(year)
            specific_date = date(year_int, 10, 1)
            return self._get_rooms_available_from_pms(
                property_id, specific_date.strftime("%Y-%m-%d")
            )
        else:
            return self._get_rooms_available_from_pms(property_id, fields.Date.today())

    # Obtiene los datos de ingresos desde contabilidad
    def _get_accounting_revenue_data(self, property_id, date_from, date_to):
        return self.get_accounting_data_from_odoo("70", date_from, date_to)

    # Obtiene los datos contables desde odoo
    def get_accounting_data_from_odoo(self, account_code, date_from, date_to):
        AccountMoveLine = self.env["account.move.line"]

        domain = [
            ("account_id.code", "=", account_code),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]

        if self.hotel:
            domain.append(("property_id", "=", self.hotel.id))

        lines = AccountMoveLine.search(domain)
        total_balance = sum(lines.mapped("balance"))

        return total_balance
