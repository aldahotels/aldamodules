# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.addons.component.core import Component


class DocuwareImporter(Component):
    _name = "docuware.cabinet.importer"
    _inherit = "docuware.importer"
    _apply_on = "docuware.cabinet"


class DocuwareMapper(Component):
    _name = "docuware.cabinet.mapper"
    _inherit = "docuware.import.mapper"
    _apply_on = "docuware.cabinet"

    direct = [("Name", "name"), ("Id", "docuware_id")]


class DocuwareBatchImporter(Component):
    _name = "docuware.cabinet.batch.importer"
    _inherit = "docuware.delayed.batch.importer"
    _apply_on = "docuware.cabinet"

    def run(self, **kwargs):
        """Run the synchronization"""
        records = self.backend_adapter.search()

        for record in records.get("FileCabinet"):
            self._import_record(record["Id"], **kwargs)
