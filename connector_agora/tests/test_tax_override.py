# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestAgoraTaxOverride(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.backend = cls.env["agora.backend"].create(
            {
                "name": "Test Agora Backend",
                "connection_type": "api",
                "api_url": "https://example.com",
                "api_token": "test-token",
            }
        )
        cls.company = cls.env.company

    def _ensure_two_sale_taxes(self):
        taxes = self.env["account.tax"].search(
            [
                ("type_tax_use", "=", "sale"),
                ("company_id", "=", self.company.id),
            ]
        )
        if len(taxes) >= 2:
            return taxes[0], taxes[1]
        if taxes:
            t0 = taxes[0]
            t1 = t0.copy({"name": t0.name + " (override)"})
            return t0, t1
        # No existing sale tax found: create a minimal pair
        t0 = self.env["account.tax"].create(
            {
                "name": "T0",
                "amount": 10.0,
                "type_tax_use": "sale",
                "company_id": self.company.id,
            }
        )
        t1 = t0.copy({"name": "T0 (override)"})
        return t0, t1

    def test_workplace_override_wins(self):
        default_tax, override_tax = self._ensure_two_sale_taxes()

        # Create company-level mapping for 10% -> default_tax
        self.env["agora.tax.mapping"].create(
            {
                "backend_id": self.backend.id,
                "company_id": self.company.id,
                "vat_rate": 0.10,
                "tax_id": default_tax.id,
            }
        )

        # Create workplace override for workplace 123 -> override_tax
        self.env["agora.tax.override"].create(
            {
                "backend_id": self.backend.id,
                "company_id": self.company.id,
                "workplace_id": 123,
                "workplace_name": "Cocina Central",
                "vat_rate": 0.10,
                "tax_id": override_tax.id,
            }
        )

        # Resolve with workplace -> should return override tax
        resolved = self.backend._resolve_tax_ids(
            0.10, company_id=self.company.id, workplace_id=123
        )
        self.assertEqual(resolved, [override_tax.id])

    def test_fallback_to_company_mapping(self):
        default_tax, _ = self._ensure_two_sale_taxes()

        # Ensure company mapping exists
        self.env["agora.tax.mapping"].create(
            {
                "backend_id": self.backend.id,
                "company_id": self.company.id,
                "vat_rate": 0.21,
                "tax_id": default_tax.id,
            }
        )

        # Resolve with a workplace that has no override -> should return company tax
        resolved = self.backend._resolve_tax_ids(
            0.21, company_id=self.company.id, workplace_id=9999
        )
        self.assertEqual(resolved, [default_tax.id])

    def test_resolve_customer_from_standard_invoice_with_existing_partner_vat_case_insensitive(
        self,
    ):
        anonymous = self.env["res.partner"].create({"name": "Anonymous Customer"})
        self.backend.anonymous_partner_id = anonymous

        existing = self.env["res.partner"].create(
            {"name": "ACME SL", "vat": "esb15876774", "customer_rank": 1}
        )

        raw = {
            "Customer": {
                "Id": "customer-123",
                "FiscalName": "ACME SL",
                "Cif": "B15876774",
                "CountryCode": "ES",
            }
        }

        resolved = self.backend._resolve_invoice_partner(raw)
        self.assertEqual(resolved, existing.id)

    def test_resolve_customer_with_vat_prefix_and_format_variations(self):
        anonymous = self.env["res.partner"].create({"name": "Anonymous Customer"})
        self.backend.anonymous_partner_id = anonymous

        existing = self.env["res.partner"].create(
            {"name": "ALUMINIOS EUROGALAN SL", "vat": "ESB15876774", "customer_rank": 1}
        )

        raw = {
            "Customer": {
                "Id": "customer-999",
                "FiscalName": "Aluminios Eurogalan S.L.",
                "Cif": "B 15 87 67 74",
                "CountryCode": "ES",
            }
        }

        resolved = self.backend._resolve_invoice_partner(raw)
        self.assertEqual(resolved, existing.id)

    def test_resolve_customer_with_country_code_prefix(self):
        anonymous = self.env["res.partner"].create({"name": "Anonymous Customer"})
        self.backend.anonymous_partner_id = anonymous

        raw = {
            "Customer": {
                "Id": "customer-456",
                "FiscalName": "Cliente PT",
                "Cif": "50030xxxx",
                "CountryCode": "PT",
            }
        }

        resolved = self.backend._resolve_invoice_partner(raw)
        partner = self.env["res.partner"].browse(resolved)
        self.assertEqual(partner.vat, "PT50030XXXX")

    def test_customer_key_case_insensitive(self):
        anonymous = self.env["res.partner"].create({"name": "Anonymous Customer"})
        self.backend.anonymous_partner_id = anonymous

        raw = {
            "customer": {
                "Id": "customer-789",
                "FiscalName": "Cliente Lowercase",
                "Cif": "X1234567Z",
                "CountryCode": "ES",
            }
        }

        resolved = self.backend._resolve_invoice_partner(raw)
        partner = self.env["res.partner"].browse(resolved)
        self.assertEqual(partner.name, "Cliente Lowercase")
        self.assertTrue(partner.vat)

    def test_anonymous_fallback_only_when_customer_missing(self):
        anonymous = self.env["res.partner"].create({"name": "Anonymous Customer"})
        self.backend.anonymous_partner_id = anonymous

        raw = {"Customer": {"Id": False, "FiscalName": "", "Cif": ""}}
        self.assertEqual(self.backend._resolve_invoice_partner(raw), anonymous.id)

        raw_missing = {"other": "value"}
        self.assertEqual(
            self.backend._resolve_invoice_partner(raw_missing), anonymous.id
        )
