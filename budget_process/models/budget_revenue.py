# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


import logging
from datetime import date, timedelta

from odoo import api, fields, models

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
            ("room_nights", "Room Nights"),
            ("occupancy", "Occupancy %"),
            ("adr", "Average Daily Rate"),
            ("room_revenue", "Room Revenue"),
            ("pax", "PAX (Guests)"),
            ("rooms_available_ly", "Rooms Available LY"),
            ("rooms_available", "Rooms Available"),
            ("rn_growth_percentage", "RN Growth % vs LY"),
            ("adr_growth_percentage", "ADR Growth % vs LY"),
            ("commission", "Commission Revenue"),
            ("revenue_percentage", "% of Total Revenue"),
            ("account_budget", "Accounting Budget"),
        ],
        required=True,
        default="room_nights",
        help="Each record type represents a different KPI calculated monthly from PMS",
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

    # Campos adicionales para análisis de crecimiento y comisiones
    rn_growth_percentage = fields.Float(
        string="RN Growth %",
        compute="_compute_growth_percentages",
        store=True,
        help="Real growth percentage for Room Nights vs Last Year",
    )
    adr_growth_percentage = fields.Float(
        string="ADR Growth %",
        compute="_compute_growth_percentages",
        store=True,
        help="Real growth percentage for ADR vs Last Year",
    )
    commission_ly = fields.Float(
        string="Commission LY",
        compute="_compute_commission_data",
        store=True,
        help="Commissions paid last year",
    )
    commission_budget = fields.Float(
        compute="_compute_commission_data",
        store=True,
        help="Budgeted commissions for current year",
    )
    revenue_percentage = fields.Float(
        string="% of Total Revenue",
        compute="_compute_revenue_percentage",
        store=True,
        help="Percentage this revenue represents of total hotel revenue",
    )

    @api.depends("record_type", "hotel", "year")
    # Calcula y distribuye los valores mensuales según el record type
    def _compute_monthly_amounts(self):

        for record in self:
            if record.record_type == "account_budget":
                continue

            monthly_values = record._get_monthly_kpi_values()
            record.update(
                {
                    "oct": monthly_values.get("oct", 0.0),
                    "nov": monthly_values.get("nov", 0.0),
                    "dec": monthly_values.get("dec", 0.0),
                    "jan": monthly_values.get("jan", 0.0),
                    "feb": monthly_values.get("feb", 0.0),
                    "mar": monthly_values.get("mar", 0.0),
                    "apr": monthly_values.get("apr", 0.0),
                    "may": monthly_values.get("may", 0.0),
                    "jun": monthly_values.get("jun", 0.0),
                    "jul": monthly_values.get("jul", 0.0),
                    "aug": monthly_values.get("aug", 0.0),
                    "sep": monthly_values.get("sep", 0.0),
                }
            )

    def _get_monthly_kpi_values(self):
        if not self.hotel or not self.year:
            return {}

        monthly_values = {}
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

        for month in months:
            month_num = self._get_month_number(month)
            year_for_month = int(self.year) if month_num >= 10 else int(self.year) + 1

            # Obtener datos históricos del año pasado
            historical_data = self._get_monthly_historical_data(
                month_num, year_for_month - 1
            )

            # Calcular valor presupuestado según el tipo de registro
            budget_value = self._calculate_budget_value_for_month(
                self.record_type, historical_data, month_num, year_for_month
            )

            monthly_values[month] = budget_value

        return monthly_values

    def _get_month_number(self, month_name):
        """Convierte nombre del mes a número"""
        month_mapping = {
            "oct": 10,
            "nov": 11,
            "dec": 12,
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
        }
        return month_mapping.get(month_name, 1)

    def _get_monthly_historical_data(self, month, year):
        """
        Obtiene datos históricos de un mes específico del PMS
        """
        try:
            first_day = date(year, month, 1)
            if month == 12:
                last_day = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = date(year, month + 1, 1) - timedelta(days=1)

            date_from = first_day.strftime("%Y-%m-%d")
            date_to = last_day.strftime("%Y-%m-%d")

            if self.env["ir.model"].search([("model", "=", "pms.reservation")]):
                return self._get_pms_reservation_data(self.hotel.id, date_from, date_to)
            else:
                revenue = self._get_accounting_revenue_data(
                    self.hotel.id, date_from, date_to
                )
                return {
                    "rooms_available": 0,
                    "room_nights": 0,
                    "room_revenue": revenue,
                    "pax": 0,
                }
        except Exception:
            return {
                "rooms_available": 0,
                "room_nights": 0,
                "room_revenue": 0,
                "pax": 0,
            }

    def _calculate_budget_value_for_month(
        self, record_type, historical_data, month, year
    ):
        """
        Calcula el valor presupuestado para un mes específico según el tipo de registro
        """
        calculation_methods = {
            "room_nights": self._calculate_room_nights_budget,
            "occupancy": self._calculate_occupancy_budget,
            "adr": self._calculate_adr_budget,
            "room_revenue": self._calculate_room_revenue_budget,
            "pax": self._calculate_pax_budget,
            "rooms_available_ly": self._calculate_rooms_available_ly,
            "rooms_available": self._calculate_rooms_available,
            "rn_growth_percentage": self._calculate_rn_growth_percentage,
            "adr_growth_percentage": self._calculate_adr_growth_percentage,
            "commission": self._calculate_commission_budget,
            "revenue_percentage": self._calculate_revenue_percentage_budget,
        }

        if record_type in calculation_methods:
            return calculation_methods[record_type](historical_data, month, year)
        return 0.0

    def _calculate_room_nights_budget(self, historical_data, month, year):
        """Calculate room nights budget value"""
        base_value = historical_data.get("room_nights", 0)
        return base_value * (1 + self.rn_growth_factor / 100)

    def _calculate_occupancy_budget(self, historical_data, month, year):
        """Calculate occupancy budget value"""
        rooms_available = self._get_current_month_rooms(month, year)
        room_nights = historical_data.get("room_nights", 0) * (
            1 + self.rn_growth_factor / 100
        )
        if rooms_available > 0:
            return min((room_nights / rooms_available) * 100, 100.0)
        return 0.0

    def _calculate_adr_budget(self, historical_data, month, year):
        """Calculate ADR budget value"""
        room_nights_ly = historical_data.get("room_nights", 0)
        room_revenue_ly = historical_data.get("room_revenue", 0)
        if room_nights_ly > 0:
            adr_ly = room_revenue_ly / room_nights_ly
            return adr_ly * (1 + self.adr_growth_factor / 100)
        return 0.0

    def _calculate_room_revenue_budget(self, historical_data, month, year):
        """Calculate room revenue budget value"""
        room_nights = historical_data.get("room_nights", 0) * (
            1 + self.rn_growth_factor / 100
        )
        room_nights_ly = historical_data.get("room_nights", 0)
        room_revenue_ly = historical_data.get("room_revenue", 0)
        if room_nights_ly > 0:
            adr_ly = room_revenue_ly / room_nights_ly
            adr_budget = adr_ly * (1 + self.adr_growth_factor / 100)
            return room_nights * adr_budget
        return 0.0

    def _calculate_pax_budget(self, historical_data, month, year):
        """Calculate PAX budget value"""
        base_value = historical_data.get("pax", 0)
        return base_value * (1 + self.rn_growth_factor / 100)

    def _calculate_rooms_available_ly(self, historical_data, month, year):
        """Calculate rooms available LY value"""
        return historical_data.get("rooms_available", 0)

    def _calculate_rooms_available(self, historical_data, month, year):
        """Calculate rooms available current year value"""
        return self._get_current_month_rooms(month, year)

    def _calculate_rn_growth_percentage(self, historical_data, month, year):
        """Calculate room nights growth percentage"""
        rn_ly = historical_data.get("room_nights", 0)
        rn_budget = rn_ly * (1 + self.rn_growth_factor / 100)
        if rn_ly > 0:
            return ((rn_budget - rn_ly) / rn_ly) * 100
        return 0.0

    def _calculate_adr_growth_percentage(self, historical_data, month, year):
        """Calculate ADR growth percentage"""
        room_nights_ly = historical_data.get("room_nights", 0)
        room_revenue_ly = historical_data.get("room_revenue", 0)
        if room_nights_ly > 0:
            adr_ly = room_revenue_ly / room_nights_ly
            adr_budget = adr_ly * (1 + self.adr_growth_factor / 100)
            if adr_ly > 0:
                return ((adr_budget - adr_ly) / adr_ly) * 100
        return 0.0

    def _calculate_commission_budget(self, historical_data, month, year):
        """Calculate commission budget value"""
        room_revenue = historical_data.get("room_revenue", 0) * (
            1 + self.services_growth_factor / 100
        )
        return room_revenue * 0.08  # 8% promedio de comisiones

    def _calculate_revenue_percentage_budget(self, historical_data, month, year):
        """Calculate revenue percentage budget value"""
        return 0.0  # Se calculará en un método separado

    def _get_current_month_rooms(self, month, year):
        """
        Obtiene el número de habitaciones disponibles para un mes específico del año actual
        """
        try:
            specific_date = date(year, month, 1)
            return self._get_rooms_available_from_pms(
                self.hotel.id, specific_date.strftime("%Y-%m-%d")
            )
        except Exception:
            return 0

    def refresh_monthly_pms_data(self):
        """
        Botón para refrescar datos mensuales del PMS
        """
        for record in self:
            if record.record_type != "account_budget":
                record._compute_monthly_amounts()

    def generate_kpi_records(self):
        """
        Genera automáticamente registros para todos los KPIs de un hotel y año
        """
        kpi_types = [
            "room_nights",
            "occupancy",
            "adr",
            "room_revenue",
            "pax",
            "rooms_available_ly",
            "rooms_available",
            "rn_growth_percentage",
            "adr_growth_percentage",
            "commission",
            "revenue_percentage",
        ]

        for record in self:
            for kpi_type in kpi_types:
                existing = self.search(
                    [
                        ("hotel", "=", record.hotel.id),
                        ("year", "=", record.year),
                        ("record_type", "=", kpi_type),
                    ]
                )

                if not existing:
                    self.create(
                        {
                            "hotel": record.hotel.id,
                            "year": record.year,
                            "record_type": kpi_type,
                            "responsible": record.responsible,
                            "description": (
                                f"{kpi_type.replace('_', ' ').title()} - "
                                f"{record.hotel.name}"
                            ),
                            "rn_growth_factor": record.rn_growth_factor,
                            "adr_growth_factor": record.adr_growth_factor,
                            "services_growth_factor": record.services_growth_factor,
                        }
                    )

    # Metodos para integracion con el pms
    def get_historical_data_from_pms(self):
        """
        Método de compatibilidad - llama al nuevo método refresh_monthly_pms_data
        """
        return self.refresh_monthly_pms_data()

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

    def calculate_revenue_percentages(self):
        for record in self:
            if record.record_type == "revenue_percentage":
                try:
                    # Buscar el registro de room_revenue para este hotel y año
                    room_revenue_record = self.search(
                        [
                            ("hotel", "=", record.hotel.id),
                            ("year", "=", record.year),
                            ("record_type", "=", "room_revenue"),
                        ],
                        limit=1,
                    )

                    if room_revenue_record and room_revenue_record.total > 0:
                        monthly_percentages = {}
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

                        for month in months:
                            room_revenue_month = getattr(room_revenue_record, month, 0)
                            # Por ahora, revenue_percentage = 100% del room revenue
                            monthly_percentages[month] = (
                                100.0 if room_revenue_month > 0 else 0.0
                            )

                        record.update(monthly_percentages)
                except Exception:
                    # Si hay error, establecer valores en 0
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
                    zero_values = {month: 0.0 for month in months}
                    record.update(zero_values)

    # Métodos de cálculo para los nuevos campos
    @api.depends(
        "record_type",
        "hotel",
        "year",
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
    )
    def _compute_growth_percentages(self):
        """
        Calcula los porcentajes de crecimiento real vs año pasado
        """
        for record in self:
            if record.record_type not in ["room_nights", "adr"]:
                record.rn_growth_percentage = 0.0
                record.adr_growth_percentage = 0.0
                continue

            try:
                # Obtener totales del año pasado
                ly_total = record._get_last_year_total()
                current_total = record.total

                if ly_total > 0:
                    growth_percentage = ((current_total - ly_total) / ly_total) * 100

                    if record.record_type == "room_nights":
                        record.rn_growth_percentage = growth_percentage
                        record.adr_growth_percentage = 0.0
                    elif record.record_type == "adr":
                        record.adr_growth_percentage = growth_percentage
                        record.rn_growth_percentage = 0.0
                else:
                    record.rn_growth_percentage = 0.0
                    record.adr_growth_percentage = 0.0
            except Exception:
                record.rn_growth_percentage = 0.0
                record.adr_growth_percentage = 0.0

    @api.depends("record_type", "hotel", "year", "total")
    def _compute_commission_data(self):
        for record in self:
            if record.record_type not in ["room_revenue", "commission"]:
                record.commission_ly = 0.0
                record.commission_budget = 0.0
                continue

            try:
                if record.record_type == "commission":
                    record.commission_budget = record.total
                    ly_total = record._get_last_year_total()
                    record.commission_ly = ly_total
                else:
                    ly_revenue = record._get_last_year_total()
                    record.commission_ly = ly_revenue * 0.08
                    record.commission_budget = record.total * 0.08
            except Exception:
                record.commission_ly = 0.0
                record.commission_budget = 0.0

    @api.depends("record_type", "hotel", "year", "total")
    def _compute_revenue_percentage(self):
        """
        Calcula el porcentaje que representa este ingreso del total de revenue del hotel
        """
        for record in self:
            if record.record_type not in ["room_revenue", "account_budget"]:
                record.revenue_percentage = 0.0
                continue

            try:
                room_revenue_record = self.search(
                    [
                        ("hotel", "=", record.hotel.id),
                        ("year", "=", record.year),
                        ("record_type", "=", "room_revenue"),
                    ],
                    limit=1,
                )

                if room_revenue_record and room_revenue_record.total > 0:
                    if record.record_type == "room_revenue":
                        record.revenue_percentage = 100.0
                    else:
                        record.revenue_percentage = (
                            record.total / room_revenue_record.total
                        ) * 100
                else:
                    record.revenue_percentage = 0.0
            except Exception:
                record.revenue_percentage = 0.0

    def _get_last_year_total(self):
        try:
            last_year = str(int(self.year) - 1)
            last_year_record = self.search(
                [
                    ("hotel", "=", self.hotel.id),
                    ("year", "=", last_year),
                    ("record_type", "=", self.record_type),
                ],
                limit=1,
            )

            if last_year_record:
                return last_year_record.total
            else:
                return self._calculate_ly_total_from_historical_data()
        except Exception:
            return 0.0

    def _calculate_ly_total_from_historical_data(self):
        try:
            last_year = int(self.year) - 1
            first_day = date(last_year, 10, 1)
            last_day = date(int(self.year), 9, 30)

            date_from = first_day.strftime("%Y-%m-%d")
            date_to = last_day.strftime("%Y-%m-%d")

            historical_data = self._get_pms_reservation_data(
                self.hotel.id, date_from, date_to
            )

            if self.record_type == "room_nights":
                return historical_data.get("room_nights", 0)
            elif self.record_type == "room_revenue":
                return historical_data.get("room_revenue", 0)
            elif self.record_type == "pax":
                return historical_data.get("pax", 0)
            elif self.record_type == "adr":
                room_nights = historical_data.get("room_nights", 0)
                room_revenue = historical_data.get("room_revenue", 0)
                if room_nights > 0:
                    return room_revenue / room_nights
                return 0.0
            else:
                return 0.0
        except Exception:
            return 0.0
