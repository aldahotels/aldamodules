# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGroupNoOne(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.Groups = cls.env["res.groups"]
        cls.no_one = cls.env.ref("base.group_no_one")
        cls.group_user = cls.env.ref("base.group_user")
        cls.group_system = cls.env.ref("base.group_system")
        cls.erp_manager = cls.env.ref("base.group_erp_manager")
        cls.template = cls.env.ref("base.default_user").with_context(active_test=False)
        # Restore the core state first: the baseline already ran when the
        # module was installed, so without this the tests would be vacuous.
        cls.group_user._apply_group(cls.no_one)
        Users = cls.env["res.users"]
        cls.plain = Users.create({"name": "Baseline Plain", "login": "bl_plain"})
        cls.admin = Users.create(
            {
                "name": "Baseline Admin",
                "login": "bl_admin",
                "groups_id": [
                    Command.link(cls.group_user.id),
                    Command.link(cls.group_system.id),
                ],
            }
        )
        cls.user_admin = Users.create(
            {
                "name": "Baseline Access Rights",
                "login": "bl_access_rights",
                "groups_id": [
                    Command.link(cls.group_user.id),
                    Command.link(cls.erp_manager.id),
                ],
            }
        )

    def _has_no_one(self, user):
        self.env.invalidate_all()
        return self.no_one in user.with_context(active_test=False).groups_id

    def _assert_baseline(self):
        self.env.invalidate_all()
        self.assertNotIn(self.no_one, self.group_user.implied_ids)
        self.assertIn(self.no_one, self.erp_manager.implied_ids)
        self.assertIn(self.no_one, self.group_system.trans_implied_ids)
        self.assertFalse(self._has_no_one(self.plain))
        self.assertFalse(self._has_no_one(self.template))
        self.assertTrue(self._has_no_one(self.admin))
        self.assertTrue(self._has_no_one(self.user_admin))

    def test_00_core_state_restored(self):
        self.assertIn(self.no_one, self.group_user.implied_ids)
        self.assertTrue(self._has_no_one(self.plain))
        self.assertTrue(self._has_no_one(self.template))

    def test_apply(self):
        self.Groups._alda_security_baseline_apply()
        self._assert_baseline()
        new_user = self.env["res.users"].create(
            {"name": "Baseline New", "login": "bl_new"}
        )
        self.assertFalse(self._has_no_one(new_user))

    def test_rerun_is_idempotent(self):
        self.Groups._alda_security_baseline_apply()
        self.env.invalidate_all()
        members = self.no_one.with_context(active_test=False).users
        self.assertFalse(self.Groups._alda_security_baseline_group_no_one())
        self.Groups._alda_security_baseline_apply()
        self.env.invalidate_all()
        self.assertEqual(self.no_one.with_context(active_test=False).users, members)
        self._assert_baseline()

    def test_rerun_cleans_explicit_membership(self):
        self.Groups._alda_security_baseline_apply()
        self.no_one.write({"users": [Command.link(self.plain.id)]})
        self.assertTrue(self._has_no_one(self.plain))
        removed = self.Groups._alda_security_baseline_group_no_one()
        self.assertEqual(removed, self.plain)
        self._assert_baseline()

    def test_rerun_after_manual_revert(self):
        self.Groups._alda_security_baseline_apply()
        # An administrator puts the implication back by hand.
        self.group_user._apply_group(self.no_one)
        self.assertTrue(self._has_no_one(self.plain))
        self.Groups._alda_security_baseline_apply()
        self._assert_baseline()

    def test_technical_features_group(self):
        tech = self.env.ref(
            "base_technical_features.group_technical_features",
            raise_if_not_found=False,
        )
        if not tech:
            self.skipTest("base_technical_features is not installed")
        self.plain.write({"groups_id": [Command.link(tech.id)]})
        self.Groups._alda_security_baseline_apply()
        self.assertTrue(self._has_no_one(self.plain))
        # The user unticks "Technical Features" in their preferences: the
        # group_no_one membership left behind goes away on the next run.
        self.plain.write({"groups_id": [Command.unlink(tech.id)]})
        self.assertTrue(self._has_no_one(self.plain))
        self.Groups._alda_security_baseline_apply()
        self.assertFalse(self._has_no_one(self.plain))

    def test_fuzzy_search_index_management(self):
        if "trgm.index" not in self.env:
            self.skipTest("base_search_fuzzy is not installed")
        TrgmIndex = self.env["trgm.index"]
        self.assertTrue(
            TrgmIndex.with_user(self.plain).check_access_rights(
                "create", raise_exception=False
            )
        )
        self.Groups._alda_security_baseline_apply()
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            TrgmIndex.with_user(self.plain).check_access_rights("create")
        self.assertTrue(
            TrgmIndex.with_user(self.admin).check_access_rights(
                "create", raise_exception=False
            )
        )

    def test_server_action(self):
        action = self.env.ref("alda_security_baseline.action_apply_security_baseline")
        with self.assertRaises(AccessError):
            action.with_user(self.plain).run()
        self.assertIn(self.no_one, self.group_user.implied_ids)
        action.with_user(self.admin).run()
        self._assert_baseline()
