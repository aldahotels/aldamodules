# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AgoraCommon


@tagged("post_install", "-at_install")
class TestAgoraTax(AgoraCommon):
    def _resolve(self, rate, workplace_id=None):
        return self.backend._resolve_tax_ids(rate, self.company.id, workplace_id)

    def test_company_mapping_and_percent_rate(self):
        self.assertEqual(self._resolve(0.10), self.tax_sale_a.ids)
        self.assertEqual(self._resolve(10.0), self.tax_sale_a.ids)

    def test_workplace_override_wins(self):
        self.env["agora.tax.override"].create(
            {
                "backend_id": self.backend.id,
                "company_id": self.company.id,
                "workplace_id": 801,
                "vat_rate": 0.10,
                "tax_id": self.tax_sale_b.id,
            }
        )
        self.assertEqual(self._resolve(0.10, 801), self.tax_sale_b.ids)
        self.assertEqual(self._resolve(0.10, 802), self.tax_sale_a.ids)

    def test_missing_mapping_raises(self):
        with self.assertRaises(UserError):
            self._resolve(0.21)

    def test_cache_invalidated_on_mapping_change(self):
        self.assertEqual(self._resolve(0.10), self.tax_sale_a.ids)
        self.tax_mapping.tax_id = self.tax_sale_b
        self.assertEqual(self._resolve(0.10), self.tax_sale_b.ids)
