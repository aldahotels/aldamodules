# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import api, fields, models

from odoo.addons.component.core import AbstractComponent

from ...components.backend_adapter import retryable_error

_logger = logging.getLogger(__name__)


class DocuwareDocument(models.AbstractModel):

    _name = "docuware.document"
    _inherit = "docuware.binding"
    _description = "Docuware document"

    docuware_document_type = fields.Char()
    cabinet_id = fields.Many2one("docuware.cabinet")

    @api.model
    def import_record(self, backend, cabinet_id, docuware_id, force=False):
        """Import a record from docuware"""
        self.check_active(backend)
        with backend.work_on(self._name) as work:
            importer = work.component(usage="record.importer")
            return importer.run(cabinet_id, docuware_id, force=force)


class DocumentAdapter(AbstractComponent):
    _name = "docuware.document.adapter"
    _inherit = "docuware.adapter"
    _docuware_path = "FileCabinets/{}/Documents"

    @retryable_error
    def read(self, cabinet_id, document_id, attributes=None):  # noqa: W8106
        """Returns the information of a record
        :rtype: dict
        """
        _logger.debug(
            "method read, model %s cabinet %s id %s, attributes %s",
            self._docuware_path,
            str(cabinet_id),
            str(document_id),
            str(attributes),
        )
        path = self._docuware_path.format(cabinet_id)
        res = self.client.get(path, document_id)
        return res

    def get_document_attachment(self, cabinet_id, document_id):
        return self.client.get_binary_data(
            "/FileCabinets/{}/Documents/{}/Data".format(cabinet_id, document_id)
        )
