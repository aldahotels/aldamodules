# © 2023 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import csv
from base64 import b64decode
from io import StringIO

from odoo import fields, models, exceptions, _


class ImportSupplierDataWizard(models.TransientModel):
    _name = "import.supplier.data.wizard"

    supplier_file = fields.Binary(required=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier')
    imported = fields.Boolean()
    product_errors = fields.Text()

    def import_data(self):
        not_found_products = []
        suppliers_reader = csv.DictReader(
            StringIO(b64decode(self.supplier_file).decode("utf-8"))
        )
        for row in suppliers_reader:
            if "reference" not in row or "stock" not in row:
                message = _("There are no reference or stock row, check the file.")
                raise exceptions.ValidationError(message)
            product_ref = row["reference"]

            product = self.env['product.supplierinfo'].search([
                ('product_code', '=', product_ref),
                ('name', '=', self.supplier_id.id)
            ], limit=1)

            if product:
                product.write({
                    "supplier_stock": row["stock"]
                })
            else:
                not_found_products.append(product_ref)
                continue

        self.product_errors = ", ".join(not_found_products)
        self.imported = True
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
