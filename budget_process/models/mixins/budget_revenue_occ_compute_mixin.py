# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models
from odoo.exceptions import UserError

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetRevenueOccupancyComputeMixin(models.AbstractModel):
    """Mixin for calculating occupancy budgeted using RN Budgeted and
    Rooms Available"""

    _name = "budget.revenue.occ.compute.mixin"
    _description = "Occupancy Budgeted Computation Mixin"

    def _get_occ_budgeted_values(self):
        "Calculate occupancy budgeted"
        monthly_values = {month: 0 for month in MONTHLY_FIELDS}

        if not self.hotel or not self.fiscal_year_id:
            _logger.warning("Missing hotel or fiscal year for occupancy calculation")
            return monthly_values

        # Find RN Budgeted record (numerador de la fórmula)
        rn_budgeted_record = self.env["budget.revenue"].search(
            [
                ("record_type", "=", "rn_budgeted"),
                ("budget_type", "=", "budgeted"),
                ("hotel", "=", self.hotel.id),
                ("fiscal_year_id", "=", self.fiscal_year_id.id),
            ],
            limit=1,
        )

        if not rn_budgeted_record:
            raise UserError(
                f"❌ No se encontró registro 'RN Budgeted' para: \n"
                f"- Hotel: {self.hotel.name}\n"
                f"- Año Fiscal: {self.fiscal_year_id.name}\n"
                f"- Tipo: Budgeted\n\n"
                f"💡 Debe crear primero el registro 'Room Nights' (rn_budgeted)"
            )

        # Find Rooms Available record (denominador de la fórmula)
        rooms_available_record = self.env["budget.revenue"].search(
            [
                ("record_type", "=", "rooms_available"),
                ("budget_type", "=", "budgeted"),
                ("hotel", "=", self.hotel.id),
                ("fiscal_year_id", "=", self.fiscal_year_id.id),
            ],
            limit=1,
        )

        if not rooms_available_record:
            raise UserError(
                f"❌ No se encontró registro 'Rooms Available' para: \n"
                f"- Hotel: {self.hotel.name}\n"
                f"- Año Fiscal: {self.fiscal_year_id.name}\n"
                f"- Tipo: Budgeted\n\n"
                f"💡 Debe crear primero el registro 'Rooms Available'"
            )

        _logger.info(
            "Found dependencies for occupancy calculation: "
            "RN Budgeted (ID: %s), Rooms Available (ID: %s)",
            rn_budgeted_record.id,
            rooms_available_record.id,
        )
        for month in MONTHLY_FIELDS:
            try:
                rn_budgeted = getattr(rn_budgeted_record, month, 0)
                rooms_available = getattr(rooms_available_record, month, 0)

                if rooms_available == 0:
                    occupancy = 0
                else:
                    occupancy_ratio = rn_budgeted / rooms_available
                    occupancy = min(occupancy_ratio, 1.0)

                monthly_values[month] = max(occupancy, 0)

                _logger.info(
                    "Occupancy %s: rn_budgeted=%.2f, rooms_available=%.2f → "
                    "occupancy=%.4f (%.2f%%)",
                    month,
                    rn_budgeted,
                    rooms_available,
                    occupancy,
                    occupancy * 100,
                )

            except Exception as e:
                _logger.error("Error calculating occupancy for %s: %s", month, e)
                monthly_values[month] = 0

        _logger.info(
            "Occupancy calculation completed for %s (fiscal %s): %s",
            self.hotel.name,
            self.fiscal_year_id.name,
            {month: f"{val: .2%}" for month, val in monthly_values.items() if val > 0},
        )

        return monthly_values

    def action_debug_occupancy_budgeted(self):
        """Debug action to show occupancy calculation details"""
        try:
            monthly_values = self._get_occ_budgeted_values()

            rn_budgeted_record = self.env["budget.revenue"].search(
                [
                    ("record_type", "=", "rn_budgeted"),
                    ("budget_type", "=", "budgeted"),
                    ("hotel", "=", self.hotel.id),
                    ("fiscal_year_id", "=", self.fiscal_year_id.id),
                ],
                limit=1,
            )

            rooms_available_record = self.env["budget.revenue"].search(
                [
                    ("record_type", "=", "rooms_available"),
                    ("budget_type", "=", "budgeted"),
                    ("hotel", "=", self.hotel.id),
                    ("fiscal_year_id", "=", self.fiscal_year_id.id),
                ],
                limit=1,
            )

            message = []
            message.append(f"🏨 OCCUPANCY BUDGETED DEBUG - {self.hotel.name}\n")
            message.append("=" * 60 + "\n\n")
            message.append("📊 FÓRMULA: MIN(RN_Budgeted / Rooms_Available, 1.0)\n\n")
            message.append("🔍 REGISTROS DEPENDIENTES:\n")
            rn_id = rn_budgeted_record.id if rn_budgeted_record else "No encontrado"
            message.append(f"• RN Budgeted (ID: {rn_id})\n")

            rooms_id = (
                rooms_available_record.id if rooms_available_record else "No encontrado"
            )
            message.append(f"• Rooms Available (ID: {rooms_id})\n")

            message.append("📈 CÁLCULO POR MES:\n")

            for month in MONTHLY_FIELDS:
                if rn_budgeted_record and rooms_available_record:
                    rn_val = getattr(rn_budgeted_record, month, 0)
                    rooms_val = getattr(rooms_available_record, month, 0)
                    occ_val = monthly_values[month]

                    if rn_val > 0 or rooms_val > 0:
                        message.append(
                            f"   {month.upper()}: {rn_val: .1f} / "
                            f"{rooms_val: .1f} = {occ_val: .2%}\n"
                        )

            message.append(
                f"\n✅ Cálculo completado para año fiscal {self.fiscal_year_id.name}\n"
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "🏨 Occupancy Budgeted Debug",
                    "message": "".join(message),
                    "type": "success",
                    "sticky": False,
                },
            }

        except Exception as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "❌ Error en Debug Occupancy",
                    "message": f"Error: {str(e)}",
                    "type": "danger",
                    "sticky": True,
                },
            }
