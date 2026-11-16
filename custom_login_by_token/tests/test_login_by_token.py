# Copyright 2026 Commit [Sun]
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The signup token opens portal accounts by link, never an internal one."""
from odoo import Command
from odoo.exceptions import AccessDenied
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoginByToken(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.portal_user = users.create(
            {
                "name": "Supplier",
                "login": "supplier@example.org",
                "groups_id": [Command.set([cls.env.ref("base.group_portal").id])],
            }
        )
        cls.internal_user = users.create(
            {
                "name": "Employee",
                "login": "employee@example.org",
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )
        (cls.portal_user | cls.internal_user).partner_id.signup_prepare()

    def _log_in_with_token(self, user):
        user.with_user(user)._check_credentials(
            user.signup_token, {"interactive": True}
        )

    def test_a_portal_user_logs_in_with_its_token(self):
        self._log_in_with_token(self.portal_user)

    def test_an_internal_user_does_not(self):
        with self.assertRaises(AccessDenied):
            self._log_in_with_token(self.internal_user)
