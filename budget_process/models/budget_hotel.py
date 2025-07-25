# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BudgetHotel(models.Model):
    _name = "budget.hotel"
    _description = "Budget Hotel Management"
    _inherit = "budget.base"

    department = fields.Selection(
        [("Hotels", "Hotels")],
        default="Hotels",
        readonly=True,
    )

    # Sincronizacion de la compañia con el hotel
    @api.onchange("hotel")
    def _onchange_hotel_sync_company(self):
        if self.hotel:
            company_id = self._get_company_from_pms_property(self.hotel)
            if company_id:
                self.company = company_id
            else:
                self.company = self.env.company.id

    # Obtiene la compañia del hotel
    def _get_company_from_pms_property(self, pms_property):
        if not pms_property:
            return False

        try:
            company_fields = ["company_id", "company", "res_company_id"]

            for field_name in company_fields:
                if hasattr(pms_property, field_name):
                    company_field = getattr(pms_property, field_name)
                    if company_field:
                        if hasattr(company_field, "id"):
                            _logger.info(
                                f"Hotel {pms_property.name}: Company synchronized "
                                f"from {field_name} -> {company_field.name}"
                            )
                            return company_field.id
                        elif isinstance(company_field, int):
                            _logger.info(
                                f"Hotel {pms_property.name}: Company ID synchronized "
                                f"from {field_name} -> {company_field}"
                            )
                            return company_field

            _logger.warning(
                f"Hotel {pms_property.name}: No company field found in PMS property"
            )
            return False

        except Exception as e:
            _logger.error(
                f"Error synchronizing company for hotel {pms_property.name}: {e}"
            )
            return False

    # sincronizar compañía al crear nuevos registros
    @api.model
    def create(self, vals):
        record = super().create(vals)

        if record.hotel and not record.company:
            record._onchange_hotel_sync_company()

        return record

    # sincronizar compañía al modificar registros
    def write(self, vals):

        result = super().write(vals)

        if "hotel" in vals:
            for record in self:
                record._onchange_hotel_sync_company()

        return result
