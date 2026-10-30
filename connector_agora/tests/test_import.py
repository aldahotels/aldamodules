# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import date
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AgoraCommon

REQUESTS_GET = "odoo.addons.connector_agora.models.agora_importer.requests.get"


@tagged("post_install", "-at_install")
class TestAgoraImport(AgoraCommon):
    def _import_day(self, invoices):
        response = MagicMock()
        response.json.return_value = {"Invoices": invoices}
        with patch(REQUESTS_GET, return_value=response):
            return self.backend._import_day_from_api(date(2026, 1, 15))

    def test_import_day_from_api(self):
        customer = {"Id": "C1", "FiscalName": "Glaucor SA", "Cif": "A12345674"}
        invoices = [
            self._raw_invoice("FV801", 7, "StandardInvoice", customer),
            self._raw_invoice("FS807", 4152, "BasicInvoice"),
        ]
        stats = self._import_day(invoices)
        self.assertEqual(stats["imported"], 2)

        bindings = self.env["agora.account.move"].search(
            [("backend_id", "=", self.backend.id)]
        )
        normal = bindings.filtered(lambda b: b.agora_series == "FV801")
        simplified = bindings - normal
        self.assertEqual(normal.journal_id, self.journal_normal)
        self.assertEqual(normal.name, "%s/2026/00007" % self.journal_normal.code)
        self.assertEqual(normal.partner_id.name, "Glaucor SA")
        self.assertEqual(normal.odoo_id.agora_invoice_ref, "FV801/7")
        self.assertEqual(normal.invoice_line_ids.tax_ids, self.tax_sale_a)
        self.assertEqual(simplified.journal_id, self.journal_simplified)
        self.assertEqual(simplified.name, "FS807/2026/04152")
        self.assertEqual(simplified.partner_id, self.anonymous)

        # Re-importing the same day does not duplicate invoices
        self._import_day(invoices)
        self.assertEqual(
            self.env["agora.account.move"].search_count(
                [("backend_id", "=", self.backend.id)]
            ),
            2,
        )

    def test_refund_uses_simplified_journal(self):
        data = self.backend._parse_agora_api_invoice(
            self._raw_invoice("RFS807", 3, "BasicRefund")
        )
        move = self.env["agora.account.move"].import_invoice_data(self.backend, data)
        self.assertEqual(move.move_type, "out_refund")
        self.assertEqual(move.journal_id, self.journal_simplified)
        self.assertEqual(move.name, "RFS807/2026/00003")

    def test_missing_journal_mapping_raises(self):
        raw = self._raw_invoice("FV999", 1, "StandardInvoice")
        raw["Workplace"]["Id"] = 999
        with self.assertRaises(UserError):
            self.backend._parse_agora_api_invoice(raw)

    def test_agora_tab_hidden_without_invoicing_group(self):
        readonly = self.env.ref("account.group_account_readonly")
        user = self.env["res.users"].create(
            {
                "name": "Readonly",
                "login": "agora_readonly",
                "groups_id": [(6, 0, readonly.ids)],
            }
        )
        arch = (
            self.env["account.move"]
            .with_user(user)
            .get_views([(False, "form")])["views"]["form"]["arch"]
        )
        self.assertNotIn("agora_bind_ids", arch)
