# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.tests import TransactionCase, tagged

from ..models.res_groups import TEMPLATE_BLOCKED_GROUPS

LOGGER = "odoo.addons.alda_security_baseline.models.res_groups"


@tagged("post_install", "-at_install")
class TestDefaultUserTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.Groups = cls.env["res.groups"]
        cls.template = cls.env.ref("base.default_user").with_context(active_test=False)
        cls.blocked = cls.Groups._alda_security_baseline_blocked_groups()
        cls.existing = cls.env["res.users"].create(
            {"name": "Baseline Existing", "login": "bl_existing"}
        )
        # Contaminate the template and an existing user with every blocked
        # group, the way installing apps does.
        cls.blocked.write(
            {
                "users": [
                    Command.link(cls.template.id),
                    Command.link(cls.existing.id),
                ]
            }
        )

    def _template_groups(self):
        self.env.invalidate_all()
        return self.template.groups_id

    def test_00_blocked_groups(self):
        for xmlid in (
            "base.group_allow_export",
            "base.group_partner_manager",
            "base.group_system",
            "base.group_erp_manager",
        ):
            self.assertIn(self.env.ref(xmlid), self.blocked)
        expected = self.Groups.browse()
        for xmlid in TEMPLATE_BLOCKED_GROUPS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                expected |= group
        self.assertEqual(self.blocked, expected)
        self.assertEqual(self.blocked, self.blocked & self._template_groups())

    def test_template_sanitized(self):
        self.Groups._alda_security_baseline_apply()
        template_groups = self._template_groups()
        for group in self.blocked:
            self.assertNotIn(
                group,
                template_groups,
                "%s is still a default group of new users" % group.full_name,
            )
        self.assertIn(self.env.ref("base.group_user"), template_groups)
        # Admin groups imply base.group_no_one: the template must not keep it.
        self.assertNotIn(self.env.ref("base.group_no_one"), template_groups)
        # Removing groups from the template never propagates to existing
        # users.
        self.assertEqual(self.blocked, self.blocked & self.existing.groups_id)
        # Effective result, implied groups included.
        new_user = self.env["res.users"].create(
            {"name": "Baseline New", "login": "bl_new"}
        )
        self.env.invalidate_all()
        self.assertFalse(self.blocked & new_user.groups_id)
        self.assertIn(self.env.ref("base.group_user"), new_user.groups_id)

    def test_rerun_is_idempotent(self):
        self.Groups._alda_security_baseline_apply()
        template_groups = self._template_groups()
        self.assertFalse(self.Groups._alda_security_baseline_sanitize_template())
        self.Groups._alda_security_baseline_apply()
        self.assertEqual(self._template_groups(), template_groups)

    def test_reimplied_group_is_kept(self):
        partner_manager = self.env.ref("base.group_partner_manager")
        implying = self.Groups.create(
            {
                "name": "Baseline implies Contact Creation",
                "implied_ids": [Command.link(partner_manager.id)],
                "users": [Command.link(self.template.id)],
            }
        )
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            removed = self.Groups._alda_security_baseline_sanitize_template()
        self.assertIn(partner_manager.full_name, "\n".join(logs.output))
        self.assertNotIn(partner_manager, removed)
        self.assertEqual(removed, self.blocked - partner_manager)
        template_groups = self._template_groups()
        self.assertIn(implying, template_groups)
        self.assertIn(partner_manager, template_groups)

    def test_template_with_roles_warns(self):
        if "res.users.role" not in self.env:
            self.skipTest("base_user_role is not installed")
        role = self.env["res.users.role"].create({"name": "Baseline Role"})
        self.env["res.users.role.line"].create(
            {"role_id": role.id, "user_id": self.template.id}
        )
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.Groups._alda_security_baseline_sanitize_template()
        self.assertIn("role lines", "\n".join(logs.output))
