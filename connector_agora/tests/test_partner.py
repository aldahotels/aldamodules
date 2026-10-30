# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import AgoraCommon


@tagged("post_install", "-at_install")
class TestAgoraPartner(AgoraCommon):
    def _resolve(self, **customer):
        return self.backend._resolve_invoice_partner(
            {"Customer": dict({"Id": "C1", "FiscalName": "Cliente"}, **customer)}
        )

    def test_existing_partner_by_vat_variants(self):
        partner = self.env["res.partner"].create({"name": "Acme", "vat": "esb15876774"})
        self.assertEqual(self._resolve(Cif="B 15.87.67-74"), partner.id)
        self.assertEqual(self._resolve(Cif="ESB15876774"), partner.id)

    def test_anonymous_without_customer_or_vat(self):
        self.assertEqual(self.backend._resolve_invoice_partner({}), self.anonymous.id)
        self.assertEqual(self._resolve(Cif=""), self.anonymous.id)

    def test_failed_partner_creation_is_rolled_back(self):
        Partner = type(self.env["res.partner"])
        with patch.object(
            Partner, "_validate_fields", side_effect=ValidationError("Invalid VAT")
        ):
            self.assertEqual(self._resolve(Cif="X9999999Z"), self.anonymous.id)
        self.assertFalse(self.env["res.partner"].search([("vat", "=", "ESX9999999Z")]))

    def test_region_exact_match_only(self):
        spain = self.env.ref("base.es")
        partner = self.env["res.partner"].browse(
            self._resolve(Cif="B70498589", CountryCode="ES", Region="a coruña")
        )
        self.assertEqual(partner.state_id, self.env.ref("base.state_es_c"))
        self.assertFalse(self.backend._find_state(spain, "Palma"))
        self.assertFalse(self.backend._find_state(spain, "A"))

    def test_existing_partner_state_not_written(self):
        partner = self.env["res.partner"].create({"name": "Acme", "vat": "ESB15876774"})
        self._resolve(Cif="B15876774", Region="a coruña")
        self.assertFalse(partner.state_id)
