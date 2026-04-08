# Copyright 2026 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    hotel = fields.Many2one(
        "pms.property",
        required=False,
        default=lambda self: self._get_default_hotel(),
    )

    def _get_default_hotel(self):
        try:
            if (
                hasattr(self.env.user, "get_active_property_ids")
                and self.env.user.get_active_property_ids()
            ):
                return self.env.user.get_active_property_ids()[0]
        except Exception as e:
            _logger.error(f"Error en _get_default_hotel: {e}")
        return False
