# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.component.core import AbstractComponent
from odoo.addons.connector.components.mapper import mapping


class DocuwareImportMapper(AbstractComponent):
    _name = "docuware.import.mapper"
    _inherit = ["base.docuware.connector", "base.import.mapper"]
    _usage = "import.mapper"

    @mapping
    def backend_id(self, record):
        return {"backend_id": self.backend_record.id}
