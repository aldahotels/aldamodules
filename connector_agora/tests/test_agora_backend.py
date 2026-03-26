# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestAgoraBackend(TransactionCase):
    """Basic tests for the Agora POS backend."""

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

    def test_backend_creation(self):
        """A backend record can be created with the required fields."""
        self.assertEqual(self.backend.name, "Test Agora Backend")
        self.assertEqual(self.backend.connection_type, "api")
        self.assertTrue(self.backend.active)

    def test_invoice_count_zero_on_creation(self):
        """A newly created backend has zero imported invoices."""
        self.assertEqual(self.backend.invoice_count, 0)

    def test_journal_mapping_creation(self):
        """A journal mapping can be linked to a backend."""
        journal = self.env["account.journal"].search([("type", "=", "sale")], limit=1)
        mapping = self.env["agora.journal.mapping"].create(
            {
                "backend_id": self.backend.id,
                "workplace_id": 1,
                "workplace_name": "Test Venue",
                "invoice_type": "simplified",
                "journal_id": journal.id,
            }
        )
        self.assertEqual(len(self.backend.agora_journal_ids), 1)
        self.assertEqual(mapping.workplace_id, 1)
