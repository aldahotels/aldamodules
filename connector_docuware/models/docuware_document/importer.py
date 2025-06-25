# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from datetime import datetime

from odoo.addons.component.core import Component

from ...components.importer import RETRY_ON_ADVISORY_LOCK


class DocuwareImporter(Component):
    _name = "docuware.document.importer"
    _inherit = "docuware.importer"

    def __init__(self, environment):
        super().__init__(environment)
        self.docuware_cabinet = None

    def run(self, cabinet_id, docuware_id, **kwargs):
        """Run the synchronization

        :param docuware_id: identifier of the record on docuware
        """
        self.docuware_id = docuware_id
        self.cabinet_id = cabinet_id
        lock_name = "import({}, {}, {}, {}, {})".format(
            self.backend_record._name,
            self.backend_record.id,
            self.model._name,
            self.cabinet_id,
            self.docuware_id,
        )
        # Keep a lock on this import until the transaction is committed
        self.advisory_lock_or_retry(lock_name, retry_seconds=RETRY_ON_ADVISORY_LOCK)
        if not self.docuware_record:
            self.docuware_record = self._get_docuware_data()
        binding = self._get_binding()
        if not binding:
            self._check_in_new_connector_env()

        skip = self._has_to_skip(binding=binding)
        if skip:
            return skip

        # import the missing linked resources
        self._import_dependencies()

        self._import(binding, **kwargs)

    def _has_to_skip(self, binding):
        """Return True if the import can be skipped"""
        if binding:
            return True

    def _get_docuware_data(self):
        """Return the raw docuware data for ``self.docuware_id``"""
        data = self.backend_adapter.read(self.cabinet_id, self.docuware_id)
        if data.get("Fields"):
            for field in data["Fields"]:
                if not field["IsNull"]:
                    if field["ItemElementName"] == "Table":
                        field_value = []
                        for element in field["Item"]["Row"]:
                            element_data = {}
                            for element_item in element["ColumnValue"]:
                                if not element_item["IsNull"]:
                                    element_data[
                                        element_item["FieldName"]
                                    ] = element_item["Item"]
                            field_value.append(element_data)
                        field["Item"] = field_value
                    if field["ItemElementName"] == "Date":
                        date_str = field["Item"]
                        date_str = date_str[6:-2]
                        field["Item"] = datetime.fromtimestamp(
                            float(date_str) / 1000.0
                        ).date()
                    data[field["FieldName"]] = field["Item"]
        return data
