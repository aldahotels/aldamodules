# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models

from odoo.addons.component.core import Component


class DocuwareCabinet(models.Model):

    _name = "docuware.cabinet"
    _inherit = "docuware.binding"
    _description = "Docuware file cabinet"

    name = fields.Char(required=True)

    def import_cabinets(self, backend_record=None, **kwargs):
        self.env["docuware.cabinet"].import_batch(
            backend=backend_record, priority=15, **kwargs
        )
        return True


class CabinetAdapter(Component):
    _name = "docuware.cabinet.adapter"
    _inherit = "docuware.adapter"
    _apply_on = "docuware.cabinet"
    _docuware_path = "FileCabinets"
