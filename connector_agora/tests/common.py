# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class AgoraCommon(AccountTestInvoicingCommon):
    """Backend with journal and tax mappings for workplace 801."""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.company = cls.company_data["company"]
        cls.journal_normal = cls.company_data["default_journal_sale"]
        cls.journal_simplified = cls.env["account.journal"].create(
            {
                "name": "Agora FS807",
                "code": "FS807",
                "type": "sale",
                "company_id": cls.company.id,
                "default_account_id": cls.company_data["default_account_revenue"].id,
            }
        )
        cls.anonymous = cls.env["res.partner"].create({"name": "Anonymous"})
        cls.backend = cls.env["agora.backend"].create(
            {
                "name": "Agora Test",
                "connection_type": "api",
                "api_url": "https://agora.example.com",
                "api_token": "token",
                "anonymous_partner_id": cls.anonymous.id,
                "agora_journal_ids": [
                    (
                        0,
                        0,
                        {
                            "workplace_id": 801,
                            "invoice_type": "normal",
                            "journal_id": cls.journal_normal.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "workplace_id": 801,
                            "invoice_type": "simplified",
                            "journal_id": cls.journal_simplified.id,
                        },
                    ),
                ],
            }
        )
        cls.tax_mapping = cls.env["agora.tax.mapping"].create(
            {
                "backend_id": cls.backend.id,
                "company_id": cls.company.id,
                "vat_rate": 0.10,
                "tax_id": cls.tax_sale_a.id,
            }
        )

    @staticmethod
    def _raw_invoice(serie, number, doc_type, customer=None):
        """Minimal invoice payload as returned by the Agora API."""
        raw = {
            "Serie": serie,
            "Number": number,
            "Date": "2026-01-15T12:00:00",
            "BusinessDay": "2026-01-15",
            "DocumentType": doc_type,
            "Workplace": {"Id": 801, "Name": "Restaurante"},
            "Pos": {"Id": 1},
            "InvoiceItems": [
                {
                    "Lines": [
                        {
                            "ProductName": "Menu",
                            "Quantity": 1,
                            "UnitPrice": 11.0,
                            "VatRate": 0.10,
                        }
                    ]
                }
            ],
        }
        if customer:
            raw["Customer"] = customer
        return raw
