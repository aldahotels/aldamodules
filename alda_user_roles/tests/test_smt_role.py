# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.pms.tests.common import TestPms

# Groups the support team must never get, whatever other modules add to the
# role later. Missing xml ids (uninstalled modules) are skipped.
DENIED_GROUPS = (
    "base.group_system",
    "base.group_erp_manager",
    "base.group_allow_export",
    "base.group_partner_manager",
    "base.group_portal",
    "base.group_public",
    "helpdesk.group_helpdesk_manager",
    "account.group_account_invoice",
    "account.group_account_readonly",
    "account.group_account_user",
    "account.group_account_manager",
    "hr.group_hr_user",
    "hr.group_hr_manager",
    "sales_team.group_sale_salesman",
    "sales_team.group_sale_salesman_all_leads",
    "sales_team.group_sale_manager",
    "pms.group_pms_user",
    "pms.group_pms_manager",
    "pms.group_pms_call",
)


@tagged("post_install", "-at_install")
class TestSmtRole(TestPms):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.role = cls.env.ref("alda_user_roles.role_smt")
        cls.company2 = cls.env["res.company"].create({"name": "Company 2"})
        cls.pms_property2 = cls.env["pms.property"].create(
            {
                "name": "Property 2",
                "company_id": cls.company2.id,
                "default_pricelist_id": cls.pricelist1.id,
            }
        )
        cls.room_type1 = cls.env["pms.room.type"].create(
            {
                "pms_property_ids": [Command.set(cls.pms_property1.ids)],
                "name": "Double",
                "default_code": "DBL",
                "class_id": cls.room_type_class1.id,
            }
        )
        cls.room1 = cls.env["pms.room"].create(
            {
                "name": "Room 101",
                "pms_property_id": cls.pms_property1.id,
                "room_type_id": cls.room_type1.id,
            }
        )
        cls.team = cls.env["helpdesk.team"].create(
            {"name": "SMT test team", "alias_name": "smt-test-team"}
        )
        cls.smt_user = cls._create_user("smt", roles=cls.role)

    @classmethod
    def _create_user(cls, login, roles=None, groups=None):
        vals = {
            "name": login,
            "login": login,
            "company_id": cls.company1.id,
            "company_ids": [Command.set(cls.company1.ids)],
            "pms_property_ids": [Command.set(cls.pms_property1.ids)],
            "pms_property_id": cls.pms_property1.id,
        }
        if groups:
            vals["groups_id"] = [Command.set(groups.ids)]
        if roles:
            vals["role_line_ids"] = [Command.create({"role_id": r.id}) for r in roles]
        return cls.env["res.users"].with_context(no_reset_password=True).create(vals)

    def _smt_env(self, model):
        self.env.invalidate_all()
        return (
            self.env[model]
            .with_user(self.smt_user)
            .with_context(
                allowed_company_ids=self.smt_user.company_ids.ids,
                allowed_pms_property_ids=self.smt_user.pms_property_ids.ids,
            )
        )

    def test_role_definition(self):
        self.assertEqual(
            self.role.group_id, self.env.ref("alda_user_roles.group_role_smt")
        )
        self.assertTrue(self.role.assignable)
        self.assertTrue(self.role.pms_all_properties)

    def test_groups_closure(self):
        group_user = self.env.ref("base.group_user")
        helpdesk_user = self.env.ref("helpdesk.group_helpdesk_user")
        allowed = (
            group_user
            | group_user.trans_implied_ids
            | helpdesk_user
            | helpdesk_user.trans_implied_ids
            | self.env.ref("alda_user_roles.group_pms_support_readonly")
            | self.env.ref("base.group_multi_company")
            | self.role.group_id
        )
        self.assertFalse(self.smt_user.groups_id - allowed)
        for xmlid in DENIED_GROUPS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                self.assertNotIn(group, self.smt_user.groups_id, xmlid)

    def test_every_property(self):
        self.assertEqual(
            self.smt_user.pms_property_ids, self.env["pms.property"].search([])
        )
        self.assertIn(self.company2, self.smt_user.company_ids)

    def test_no_business_access(self):
        for model in (
            "pms.folio",
            "pms.reservation",
            "account.move",
            "account.payment",
            # hr.employee is not listed: Odoo serves hr.employee.public to
            # users without HR rights instead of raising.
            "hr.contract",
            "hr.payslip",
        ):
            if model not in self.env:
                continue
            with self.assertRaises(AccessError, msg=model):
                self._smt_env(model).search([], limit=1)
        with self.assertRaises(AccessError):
            self._smt_env("pms.property").browse(self.pms_property1.id).write(
                {"name": "Renamed"}
            )

    def test_ticket_with_hotel_and_room(self):
        Ticket = self._smt_env("helpdesk.ticket")
        ticket = Ticket.create(
            {
                "name": "Broken lamp",
                "team_id": self.team.id,
                "pms_property_id": self.pms_property1.id,
                "pms_room_id": self.room1.id,
            }
        )
        ticket.write({"name": "Broken lamp in room"})
        self.env.invalidate_all()
        self.assertEqual(ticket.pms_room_id.display_name, self.room1.display_name)
        self.assertEqual(ticket.pms_property_id.name, self.pms_property1.name)

    def test_dropdowns(self):
        properties = self._smt_env("pms.property").name_search("Property")
        self.assertIn(self.pms_property2.id, [pid for pid, _name in properties])
        rooms = self._smt_env("pms.room").name_search("101")
        self.assertIn(self.room1.id, [rid for rid, _name in rooms])

    def test_profile_manager_assigns_smt(self):
        manager = self._create_user(
            "manager",
            groups=self.env.ref("pms_user_roles.group_role_manager")
            | self.env.ref("base.group_user"),
        )
        target = self._create_user(
            "target", roles=self.env.ref("pms_user_roles.role_internal_base")
        )
        self.env.invalidate_all()
        self.env["res.users.role.line"].with_user(manager).create(
            {"user_id": target.id, "role_id": self.role.id}
        )
        self.assertTrue(target.has_group("helpdesk.group_helpdesk_user"))
        self.assertEqual(target.pms_property_ids, self.env["pms.property"].search([]))
