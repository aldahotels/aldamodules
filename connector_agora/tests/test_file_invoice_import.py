# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import logging
import os
import tempfile

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestFileInvoiceImportPartnerAssignment(TransactionCase):
    """End-to-end coverage for the user story:
    Agora - parse file - resolve/create partner - create account.move.
    The resulting invoice MUST be assigned to the real customer, not to the
    anonymous customer, whenever the file source provides enough data.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.anonymous_partner = cls.env["res.partner"].create(
            {
                "name": "Anonymous (E2E)",
                "is_company": True,
                "customer_rank": 1,
            }
        )
        # Sale journal (required for account.move)
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "sale")], limit=1
        )
        cls.company = cls.journal.company_id or cls.env.company
        # Backend with a temporary export folder so file mode constraints pass.
        cls.tmpdir = tempfile.mkdtemp(prefix="connector_agora_test_")
        cls.backend = cls.env["agora.backend"].create(
            {
                "name": "File Backend E2E",
                "connection_type": "file",
                "export_folder_path": cls.tmpdir,
                "file_format": "xml",
                "anonymous_partner_id": cls.anonymous_partner.id,
            }
        )
        # Tax mappings required by _resolve_tax_ids when parsing invoice lines.
        cls.tax_21 = cls.env["account.tax"].create(
            {
                "name": "IVA 21% (Test)",
                "amount": 21.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "company_id": cls.company.id,
            }
        )
        cls.tax_10 = cls.env["account.tax"].create(
            {
                "name": "IVA 10% (Test)",
                "amount": 10.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "company_id": cls.company.id,
            }
        )
        for rate, tax in ((0.21, cls.tax_21), (0.10, cls.tax_10)):
            cls.env["agora.tax.mapping"].create(
                {
                    "backend_id": cls.backend.id,
                    "company_id": cls.company.id,
                    "vat_rate": rate,
                    "tax_id": tax.id,
                }
            )
        cls.env["agora.journal.mapping"].create(
            {
                "backend_id": cls.backend.id,
                "workplace_id": 801,
                "invoice_type": "normal",
                "journal_id": cls.journal.id,
            }
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # Best-effort cleanup of the temp dir.
        try:
            for f in os.listdir(cls.tmpdir):
                os.remove(os.path.join(cls.tmpdir, f))
            os.rmdir(cls.tmpdir)
        except OSError as error:
            _logger.warning(
                "Could not clean up temporary directory: %s",
                error,
            )

    def _write_invoice_json(self, payload):
        path = os.path.join(self.tmpdir, "test_invoice.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_json_normal_invoice_only_customer_id_falls_back_to_anonymous(self):
        """JSON file with only 'CustomerId' (no full Customer dict) cannot be
        safely resolved, so the anonymous partner is used."""
        self._write_invoice_json(
            {
                "Id": "FILE-JSON-002",
                "Series": "FV",
                "Number": "2",
                "Date": "2026-01-15",
                "Type": "invoice",
                "CustomerId": "42",
                "Lines": [
                    {
                        "Description": "Item",
                        "Quantity": 1,
                        "UnitPrice": 10,
                        "TaxRate": 21,
                    }
                ],
            }
        )
        invoices = self.backend._parse_json_file(
            os.path.join(self.tmpdir, "test_invoice.json")
        )
        self.assertEqual(invoices[0]["partner_id"], self.anonymous_partner.id)
        agora_move = self.env["agora.account.move"].import_invoice_data(
            self.backend, invoices[0]
        )
        self.assertEqual(agora_move.odoo_id.partner_id, self.anonymous_partner)

    def test_json_api_format_standard_invoice_assigns_new_partner(self):
        """Real Agora API payload: DocumentType=StandardInvoice, Customer dict,
        Workplace/Pos dicts and InvoiceItems[].Lines resolves the real customer
        and keeps the binding linked to that partner instead of the anonymous one."""
        raw = {
            "Id": "FILE-JSON-API-001",
            "Serie": "FV801",
            "Number": 7,
            "Date": "2026-01-15",
            "BusinessDay": "2026-01-14",
            "DocumentType": "StandardInvoice",
            "Workplace": {
                "Id": 801,
                "Name": "RESTAURANTE PUNTA DEL ESTE",
            },
            "Pos": {"Id": 1},
            "Customer": {
                "Id": "2002000093",
                "FiscalName": "GLAUCOR SA",
                "Cif": "A12345674",
                "CountryCode": "ES",
                "City": "PAMPLONA",
                "ZipCode": "31003",
            },
            "InvoiceItems": [
                {
                    "Discounts": {"DiscountRate": 0.0},
                    "Lines": [
                        {
                            "ProductName": "Producto 1",
                            "Quantity": 1,
                            "UnitPrice": 10.5,
                            "VatRate": 0.10,
                        }
                    ],
                }
            ],
        }
        invoice_data = self.backend._parse_agora_api_invoice(raw)
        self.assertEqual(invoice_data["agora_document_type"], "normal")
        self.assertEqual(invoice_data["agora_workplace_id"], 801)
        self.assertEqual(
            invoice_data["agora_workplace_name"], "RESTAURANTE PUNTA DEL ESTE"
        )
        self.assertEqual(invoice_data["agora_pos_id"], 1)
        self.assertEqual(invoice_data["agora_customer_id"], "2002000093")
        self.assertEqual(len(invoice_data["lines"]), 1)
        self.assertEqual(invoice_data["lines"][0]["price_unit"], 10.5)
        self.assertTrue(invoice_data.get("partner_id"))
        self.assertNotEqual(invoice_data["partner_id"], self.anonymous_partner.id)

        agora_move = self.env["agora.account.move"].import_invoice_data(
            self.backend, invoice_data
        )
        self.assertNotEqual(agora_move.odoo_id.partner_id, self.anonymous_partner)
        self.assertEqual(agora_move.odoo_id.partner_id.name, "GLAUCOR SA")
        self.assertEqual(agora_move.agora_customer_id, "2002000093")

    def test_json_api_format_basic_refund_assigns_existing_partner_by_vat(self):
        """Rectification / refund invoices still include the customer fiscal ID and
        must resolve the real partner instead of anonymous."""
        existing = self.env["res.partner"].create(
            {
                "name": "inxenia gestion proyecto obra slu",
                "vat": "ESB70498589",
                "customer_rank": 1,
            }
        )

        raw = {
            "Id": "FILE-JSON-API-REFUND-001",
            "Serie": "RFC4232026",
            "Number": 274,
            "BusinessDay": "2026-04-30",
            "Date": "2026-04-30T13:11:12",
            "DocumentType": "BasicRefund",
            "Customer": {
                "Id": 2002000039,
                "FiscalName": "inxenia gestion proyecto obra slu",
                "Cif": "B70498589",
                "Street": "rua do horreo 11",
                "City": "carballo",
                "Region": "a coruña",
                "ZipCode": "15100",
                "CountryCode": "ES",
            },
            "Workplace": {"Id": 2, "Name": "RESTAURANTE PUNTA DEL ESTE"},
            "Pos": {"Id": 9},
            "RelatedInvoice": {"Serie": "FC4232026", "Number": 11918},
            "InvoiceItems": [
                {
                    "Discounts": {"DiscountRate": 0.0},
                    "Lines": [
                        {
                            "ProductName": "Producto rectificativo",
                            "Quantity": 1,
                            "UnitPrice": 10.5,
                            "VatRate": 0.21,
                        }
                    ],
                }
            ],
        }

        invoice_data = self.backend._parse_agora_api_invoice(raw)
        self.assertEqual(invoice_data["agora_document_type"], "rectification")
        self.assertEqual(invoice_data["partner_id"], existing.id)
        self.assertNotEqual(invoice_data["partner_id"], self.anonymous_partner.id)
