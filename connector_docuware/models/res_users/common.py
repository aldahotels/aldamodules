# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def get_active_property_ids(self):
        super_properties = super().get_active_property_ids()
        if "default_pms_property_id" in self._context:
            return [self._context.get("default_pms_property_id")]
        return super_properties
