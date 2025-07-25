# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BudgetRN(models.Model):
    _name = "budget.rn"
    _description = "Budget Room Nights"
    _inherit = "budget.base"
    _rec_name = "name"

    name = fields.Char(
        compute="_compute_name",
        store=True,
        readonly=True,
    )

    hotel_id = fields.Char(
        string="Hotel ID",
        compute="_compute_hotel_id_from_budget",
        store=True,
        help="ID del hotel sincronizado desde budget.hotel",
    )

    # Campos específicos para Room Nights
    record_type = fields.Selection(
        [
            ("actual_data", "Actual Data"),
            ("budget_data", "Budget Data"),
        ],
        default="actual_data",
        required=True,
        help="Record type: pms current data or budgeted data",
    )

    # Campos que obtienen datos del pms automáticamente
    oct_actual = fields.Float(
        string="Oct (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of Octobre",
    )
    nov_actual = fields.Float(
        string="Nov (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of November",
    )
    dec_actual = fields.Float(
        string="Dec (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of December",
    )
    jan_actual = fields.Float(
        string="Jan (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of January",
    )
    feb_actual = fields.Float(
        string="Feb (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of February",
    )
    mar_actual = fields.Float(
        string="Mar (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of March",
    )
    apr_actual = fields.Float(
        string="Apr (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of April",
    )
    may_actual = fields.Float(
        string="May (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of May",
    )
    jun_actual = fields.Float(
        string="Jun (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of June",
    )
    jul_actual = fields.Float(
        string="Jul (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of July",
    )
    aug_actual = fields.Float(
        string="Aug (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of August",
    )
    sep_actual = fields.Float(
        string="Sep (Actual)",
        compute="_compute_monthly_actual_data",
        store=True,
        help="Room nights current of September",
    )

    total_actual = fields.Float(
        compute="_compute_total_actual",
        store=True,
        help="Total room nights current year",
    )

    @api.depends("hotel")
    # Calcula el hotel_id desde budget.hotel
    def _compute_hotel_id_from_budget(self):
        for record in self:
            if record.hotel:
                budget_hotel = self.env["budget.hotel"].search(
                    [("hotel", "=", record.hotel.id)], limit=1
                )

                if budget_hotel and budget_hotel.hotel_id:
                    record.hotel_id = budget_hotel.hotel_id
                else:
                    record.hotel_id = False
            else:
                record.hotel_id = False

    @api.onchange("hotel")
    # Sincroniza el hotel_id con el configurado en budget.hotel
    def _onchange_hotel_sync_budget_hotel(self):
        if self.hotel:
            budget_hotel = self.env["budget.hotel"].search(
                [("hotel", "=", self.hotel.id)], limit=1
            )

            if budget_hotel:
                self.hotel_id = budget_hotel.hotel_id
            else:
                self.hotel_id = False
        else:
            self.hotel_id = False

    # Botón para refrescar datos del pms
    def refresh_pms_data(self):
        self._compute_monthly_actual_data()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Datos Actualizados",
                "message": "The PMS data has been updated successfully.",
                "type": "success",
                "sticky": False,
            },
        }

    @api.depends("hotel", "year", "record_type")
    # calcula el nombre del registro
    def _compute_name(self):
        for record in self:
            if record.hotel and record.year:
                record_type_label = dict(record._fields["record_type"].selection).get(
                    record.record_type, ""
                )
                record.name = (
                    f"RN {record.hotel.name} {record.year} ({record_type_label})"
                )
            else:
                record.name = "New Room Nights"

    # Lista de meses del año fiscal 
    fiscal_months = [
        "oct", "nov", "dec", "jan", "feb", "mar",
        "apr", "may", "jun", "jul", "aug", "sep"
    ]

    @api.depends("hotel", "year")
    # Calcula los datos mensuales reales desde el PMS
    def _compute_monthly_actual_data(self):
        for record in self:
            if not record._should_compute_actual_data():
                record._reset_monthly_actual_fields()
                continue

            try:
                year_int = int(record.year)
                monthly_data = record._get_monthly_nights_from_pms(
                    record.hotel.id, year_int
                )
                record._update_monthly_actual_fields(monthly_data)

            except Exception as e:
                _logger.warning(
                    f"Error getting monthly PMS data for "
                    f"{record.hotel.name} {record.year}: {e}"
                )
                record._reset_monthly_actual_fields()

    # Determina si se deben calcular los datos actuales
    def _should_compute_actual_data(self):
        return (
            self.hotel 
            and self.year 
            and self.record_type == "actual_data"
        )

    # Resetea todos los campos mensuales actuales a cero
    def _reset_monthly_actual_fields(self):
        for month in self.fiscal_months:
            setattr(self, f"{month}_actual", 0.0)

    # Actualiza los campos mensuales con los datos obtenidos
    def _update_monthly_actual_fields(self, monthly_data):
        for month in self.fiscal_months:
            nights = monthly_data.get(month, 0.0)
            setattr(self, f"{month}_actual", nights)

    @api.depends(
        "oct_actual",
        "nov_actual",
        "dec_actual",
        "jan_actual",
        "feb_actual",
        "mar_actual",
        "apr_actual",
        "may_actual",
        "jun_actual",
        "jul_actual",
        "aug_actual",
        "sep_actual",
    )
    # Calcula el total de noches actuales
    def _compute_total_actual(self):
        for record in self:
            record.total_actual = sum(
                [
                    record.oct_actual,
                    record.nov_actual,
                    record.dec_actual,
                    record.jan_actual,
                    record.feb_actual,
                    record.mar_actual,
                    record.apr_actual,
                    record.may_actual,
                    record.jun_actual,
                    record.jul_actual,
                    record.aug_actual,
                    record.sep_actual,
                ]
            )

    # Obtiene las noches vendidas por mes desde el PMS
    def _get_monthly_nights_from_pms(self, property_id, year):
        if not self.env.get("pms.reservation"):
            _logger.warning("Modelo pms.reservation no disponible")
            return {month: 0.0 for month in self.fiscal_months}

        PmsReservation = self.env["pms.reservation"]
        monthly_data = {}
        
        # Mapeo de meses fiscales a números
        month_mapping = {
            "oct": 10, "nov": 11, "dec": 12,
            "jan": 1, "feb": 2, "mar": 3,
            "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9
        }

        for month_name in self.fiscal_months:
            month_num = month_mapping[month_name]
            try:
                nights = self._get_nights_for_month(
                    PmsReservation, property_id, year, month_num
                )
                monthly_data[month_name] = nights

                query_year = year - 1 if month_num >= 10 else year
                _logger.info(
                    f"Hotel {property_id}, {month_name} {query_year}: {nights} nights"
                )

            except Exception as e:
                _logger.warning(f"Error obteniendo datos para {month_name} {year}: {e}")
                monthly_data[month_name] = 0.0

        return monthly_data

    # Obtiene las noches para un mes específico
    def _get_nights_for_month(self, PmsReservation, property_id, year, month_num):

        query_year = year - 1 if month_num >= 10 else year
        date_from = date(query_year, month_num, 1)
        if month_num == 12:
            date_to = date(query_year + 1, 1, 1) - relativedelta(days=1)
        else:
            date_to = date(query_year, month_num + 1, 1) - relativedelta(days=1)

        domain = [
            ("property_id", "=", property_id),
            ("checkin", ">=", date_from.strftime("%Y-%m-%d")),
            ("checkin", "<=", date_to.strftime("%Y-%m-%d")),
            ("state", "!=", "cancelled"),
        ]

        reservations = PmsReservation.search(domain)
        
        total_nights = sum(
            reservation.nights
            for reservation in reservations
            if hasattr(reservation, "nights")
        )
        
        return total_nights

    @api.model
    # Crea registros de presupuesto para todos los hoteles
    def create_budget_records_for_all_hotels(self, year):
        hotels = self.env["pms.property"].search([])
        created_records = []

        for hotel in hotels:
            actual_record = self.create(
                {
                    "hotel": hotel.id,
                    "year": str(year),
                    "record_type": "actual_data",
                    "description": f"Room Nights datos reales {hotel.name} {year}",
                }
            )
            created_records.append(actual_record)
            budget_record = self.create(
                {
                    "hotel": hotel.id,
                    "year": str(year),
                    "record_type": "budget_data",
                    "description": f"Room Nights presupuesto {hotel.name} {year}",
                }
            )
            created_records.append(budget_record)

        return created_records
