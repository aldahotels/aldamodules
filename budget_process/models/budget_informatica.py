# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import date

from odoo import api, fields, models


class BudgetInformatica(models.Model):
    _name = "budget.informatica"
    _description = "IT budget"
    _inherit = "budget.base"

    department = fields.Selection(
        [("informatica", "Informática")],
        default="informatica",
        readonly=True,
    )

    # Campo para diferenciar el tipo de registro
    record_type = fields.Selection(
        [
            ("per_room", "Per Room Calculation"),
            ("distributed", "Distributed Amount"),
        ],
        required=True,
        default="manual",
        help=(
            "Per Room: Multiply amount by number of rooms."
            " Distributed: Divide total amount across 12 months"
        ),
    )

    # Datos del año actual - número de habitaciones disponibles
    rooms_available_current = fields.Float(
        string="Rooms Available Current Year",
        compute="_compute_current_year_data",
        store=True,
        help="Available rooms current year (from PMS)",
    )

    # Campos calculados de informatica
    manual_amount = fields.Float(
        string="Amount",
        help="Amount to be used for calculations (per room or total distributed)",
    )

    @api.depends("hotel", "fiscal_year_id", "record_type")
    # Calcula automáticamente los datos del año actual desde PMS
    def _compute_current_year_data(self):

        for record in self:
            if not record.hotel:
                record.rooms_available_current = 0.0
                continue

            try:
                fiscal_year = record.fiscal_year_id
                if fiscal_year:
                    year_int = fiscal_year.date_from.year
                    current_rooms = record._get_current_year_rooms_from_pms(
                        record.hotel.id, year_int
                    )
                    record.rooms_available_current = current_rooms
                else:
                    record.rooms_available_current = 0.0
            except Exception:
                record.rooms_available_current = 0.0

    @api.depends("record_type", "manual_amount", "rooms_available_current")
    # Calcula los montos mensuales según el tipo de registro
    def _compute_monthly_amounts(self):
        for record in self:
            if record.record_type == "manual":
                continue
            elif record.record_type == "per_room":
                monthly_amount = record.manual_amount * record.rooms_available_current
                record.update(
                    {
                        "oct": monthly_amount,
                        "nov": monthly_amount,
                        "dec": monthly_amount,
                        "jan": monthly_amount,
                        "feb": monthly_amount,
                        "mar": monthly_amount,
                        "apr": monthly_amount,
                        "may": monthly_amount,
                        "jun": monthly_amount,
                        "jul": monthly_amount,
                        "aug": monthly_amount,
                        "sep": monthly_amount,
                    }
                )
            elif record.record_type == "distributed":
                monthly_amount = (
                    record.manual_amount / 12.0 if record.manual_amount else 0.0
                )
                record.update(
                    {
                        "oct": monthly_amount,
                        "nov": monthly_amount,
                        "dec": monthly_amount,
                        "jan": monthly_amount,
                        "feb": monthly_amount,
                        "mar": monthly_amount,
                        "apr": monthly_amount,
                        "may": monthly_amount,
                        "jun": monthly_amount,
                        "jul": monthly_amount,
                        "aug": monthly_amount,
                        "sep": monthly_amount,
                    }
                )

    @api.onchange("record_type", "manual_amount", "rooms_available_current")
    # Recalcular cuando cambian los valores relevantes
    def _onchange_compute_monthly_amounts(self):
        self._compute_monthly_amounts()

    # Métodos para integración con PMS
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

    # Obtiene el número de habitaciones disponibles del PMS para el año actual
    def _get_current_year_rooms_from_pms(self, property_id, year=None):
        if year:
            specific_date = date(year, 10, 1)
            return self._get_rooms_available_from_pms(
                property_id, specific_date.strftime("%Y-%m-%d")
            )
        else:
            return self._get_rooms_available_from_pms(property_id, fields.Date.today())

    # Método para obtener el ID de la compañía
    def write(self, vals):
        result = super().write(vals)
        fields_to_check = {"record_type", "manual_amount", "rooms_available_current"}
        if fields_to_check.intersection(vals.keys()):
            for record in self:
                record._compute_monthly_amounts()
        return result
