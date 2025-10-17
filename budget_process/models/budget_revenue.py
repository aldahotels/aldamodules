# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

from .budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetRevenue(models.Model):
    _name = "budget.revenue"
    _description = "Revenue budget"
    _inherit = [
        "budget.base",
        "budget.calculation.mixin",
        "budget.revenue.validation.mixin",
        "budget.revenue.rn.compute.mixin",
        "budget.revenue.actions.mixin",
        "budget.revenue.rn.actions.mixin",
        "budget.revenue.percentage.actions.mixin",
        "budget.revenue.rn.budgeted.actions.mixin",
        "budget.revenue.occ.compute.mixin",
        "budget.revenue.pax.compute.mixin",
    ]

    department = fields.Selection(
        [("revenue", "Revenue")], default="revenue", readonly=True
    )

    record_type = fields.Selection(
        [
            ("rooms_available_ly", "Rooms Available LY"),
            ("rooms_available", "Rooms Available"),
            ("rn_ly", "Room Nights LY"),
            ("increase_decrease_rn_ly", "increase or decrease RN LY"),
            ("rn_budgeted", "Room Nights"),
            ("occ_budgeted", "Occuppancy"),
            ("pax_budgeted", "Pax"),
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

    percentage_increase_decrease = fields.Float(
        string="Percentage (%)",
        help=("Percentage for increase/decrease RN LY calculation. "),
        digits=(5, 2),  # 5 dígitos totales, 2 decimales (ej: 125.50%)
    )

    @api.depends(
        "record_type",
        "budget_type",
        "hotel",
        "fiscal_year_id",
        "percentage_increase_decrease",
    )
    def _compute_monthly_amounts(self):
        "Compute monthly amounts based on record_type and budget_type"
        for record in self:
            _logger.info(
                "COMPUTE: Processing record ID %s, record_type=%s, budget_type=%s",
                record.id,
                record.record_type,
                record.budget_type,
            )

            monthly_values = {month: 0 for month in MONTHLY_FIELDS}

            # Handle different record types that need data from budget.data
            if record.budget_type == "budgeted":
                if record.record_type in ["rooms_available", "rooms_available_ly"]:
                    _logger.info(
                        "COMPUTE: Getting rooms available data for record %s", record.id
                    )
                    monthly_values = record._get_rooms_available_from_budget_data(
                        "[REVENUE]"
                    )
                elif record.record_type == "rn_ly":
                    _logger.info(
                        "COMPUTE: Getting room nights data for record %s", record.id
                    )
                    monthly_values = record._get_rooms_nights_from_budget_data()
                elif record.record_type == "rn_budgeted":
                    _logger.info(
                        "COMPUTE: Getting RN budgeted values for record %s", record.id
                    )
                    monthly_values = record._get_rn_budgeted_values()
                    _logger.info(
                        "COMPUTE: RN budgeted result for record %s: %s",
                        record.id,
                        monthly_values,
                    )
                elif record.record_type == "occ_budgeted":
                    _logger.info(
                        "COMPUTE: Getting occupancy budgeted values for record %s",
                        record.id,
                    )
                    monthly_values = record._get_occ_budgeted_values()
                    _logger.info(
                        "COMPUTE: Occupancy budgeted result for record %s: %s",
                        record.id,
                        monthly_values,
                    )
                elif record.record_type == "pax_budgeted":
                    _logger.info(
                        "COMPUTE: Getting pax budgeted values for record %s", record.id
                    )
                    monthly_values = record._get_pax_budgeted_values()
                    _logger.info(
                        "COMPUTE: Pax budgeted result for record %s: %s",
                        record.id,
                        monthly_values,
                    )

            if record.record_type == "increase_decrease_rn_ly":
                _logger.info(
                    "COMPUTE: Getting increase/decrease values for record %s", record.id
                )
                monthly_values = record._get_increase_decrease_rn_ly_values()

            _logger.info(
                "COMPUTE: Final monthly values for record %s: %s",
                record.id,
                monthly_values,
            )

            for month in MONTHLY_FIELDS:
                old_value = getattr(record, month, 0)
                new_value = monthly_values[month]
                setattr(record, month, new_value)
                _logger.info(
                    "COMPUTE: Record %s, %s: %s → %s",
                    record.id,
                    month,
                    old_value,
                    new_value,
                )

    @api.onchange("percentage_increase_decrease")
    def _onchange_percentage_increase_decrease(self):
        "Recalculate monthly amounts when percentage changes"
        if self._is_increase_decrease_rn_ly_budgeted():
            self._compute_monthly_amounts()
