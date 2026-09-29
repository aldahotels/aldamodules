from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTicketPropertySecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, no_reset_password=True)
        )
        cls.company = cls.env.ref("base.main_company")
        cls.property_a = cls.env.ref("pms.main_pms_property")
        cls.property_b = cls.env["pms.property"].create(
            {
                "name": "Test Property B",
                "company_id": cls.company.id,
                "default_pricelist_id": cls.env.ref("product.list0").id,
            }
        )
        user_vals = {
            "company_id": cls.company.id,
            "company_ids": [(6, 0, cls.company.ids)],
        }
        # Fixture tickets are created by a user who holds both properties:
        # the property constraint validates against the env user.
        cls.creator = new_test_user(
            cls.env,
            login="alda_hd_creator",
            groups="helpdesk.group_helpdesk_manager,pms.group_pms_user",
            pms_property_ids=[(6, 0, (cls.property_a | cls.property_b).ids)],
            pms_property_id=cls.property_a.id,
            **user_vals,
        )
        cls.user_a = new_test_user(
            cls.env,
            login="alda_hd_user_a",
            groups="helpdesk.group_helpdesk_user,pms.group_pms_user",
            pms_property_ids=[(6, 0, cls.property_a.ids)],
            pms_property_id=cls.property_a.id,
            **user_vals,
        )
        cls.user_none = new_test_user(
            cls.env,
            login="alda_hd_user_none",
            groups="helpdesk.group_helpdesk_user,pms.group_pms_user",
            **user_vals,
        )
        Team = cls.env["helpdesk.team"]
        cls.team_internal = Team.create(
            {
                "name": "Test Internal Team",
                "privacy_visibility": "internal",
                "member_ids": [(6, 0, cls.creator.ids)],
            }
        )
        cls.team_invited = Team.create(
            {
                "name": "Test Invited Team",
                "privacy_visibility": "invited_internal",
                "member_ids": [(6, 0, cls.creator.ids)],
            }
        )
        cls.ticket_a = cls._create_ticket(cls.team_internal, cls.property_a)
        cls.ticket_b = cls._create_ticket(cls.team_internal, cls.property_b)
        cls.ticket_none = cls._create_ticket(cls.team_internal, False)
        cls.ticket_a_invited = cls._create_ticket(cls.team_invited, cls.property_a)

    @classmethod
    def _create_ticket(cls, team, pms_property):
        # The creator is explicitly assigned so that no test user becomes a
        # follower through auto-assignment.
        return (
            cls.env["helpdesk.ticket"]
            .with_user(cls.creator)
            .sudo()
            .create(
                {
                    "name": "Test ticket",
                    "team_id": team.id,
                    "user_id": cls.creator.id,
                    "pms_property_id": pms_property.id if pms_property else False,
                }
            )
        )

    def _search_as(self, user, model, domain):
        self.env.invalidate_all()
        return self.env[model].with_user(user).search(domain)

    def test_allowed_properties_without_context(self):
        Ticket = self.env["helpdesk.ticket"].with_user(self.creator)
        self.assertEqual(
            sorted(Ticket._get_allowed_property_ids()),
            sorted((self.property_a | self.property_b).ids),
        )

    def test_context_narrows_allowed_properties(self):
        Ticket = (
            self.env["helpdesk.ticket"]
            .with_user(self.creator)
            .with_context(allowed_pms_property_ids=self.property_b.ids)
        )
        self.assertEqual(Ticket._get_allowed_property_ids(), self.property_b.ids)

    def test_context_cannot_add_properties(self):
        Ticket = (
            self.env["helpdesk.ticket"]
            .with_user(self.user_a)
            .with_context(
                allowed_pms_property_ids=(self.property_a | self.property_b).ids
            )
        )
        self.assertEqual(Ticket._get_allowed_property_ids(), self.property_a.ids)

    def test_spoofed_context_cannot_move_ticket(self):
        ticket = self.ticket_a.with_user(self.user_a).with_context(
            allowed_pms_property_ids=self.property_b.ids
        )
        with self.assertRaises(ValidationError):
            ticket.write({"pms_property_id": self.property_b.id})

    def test_create_with_own_property(self):
        ticket = (
            self.env["helpdesk.ticket"]
            .with_user(self.user_a)
            .with_context(allowed_pms_property_ids=self.property_a.ids)
            .create(
                {
                    "name": "Own property ticket",
                    "team_id": self.team_internal.id,
                    "pms_property_id": self.property_a.id,
                }
            )
        )
        self.assertEqual(ticket.pms_property_id, self.property_a)

    def test_property_field_domain(self):
        fields = (
            self.env["helpdesk.ticket"]
            .with_user(self.user_a)
            .fields_get(["pms_property_id"])
        )
        self.assertEqual(
            fields["pms_property_id"]["domain"],
            [("id", "in", self.property_a.ids)],
        )

    def test_group_rule_removed(self):
        self.assertFalse(
            self.env.ref(
                "alda_helpdesk_pms_enterprise.helpdesk_ticket_user_pms_property",
                raise_if_not_found=False,
            )
        )

    def test_team_privacy_applies_to_non_managers(self):
        found = self._search_as(
            self.user_a,
            "helpdesk.ticket",
            [("id", "in", (self.ticket_a | self.ticket_a_invited).ids)],
        )
        self.assertEqual(found.ids, self.ticket_a.ids)
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            self.ticket_a_invited.with_user(self.user_a).read(["name"])

    def test_property_rule_hides_foreign_tickets(self):
        tickets = self.ticket_a | self.ticket_b | self.ticket_none
        found = self._search_as(
            self.user_a, "helpdesk.ticket", [("id", "in", tickets.ids)]
        )
        self.assertEqual(
            sorted(found.ids), sorted((self.ticket_a | self.ticket_none).ids)
        )

    def test_user_without_properties_sees_tickets_without_property(self):
        tickets = self.ticket_a | self.ticket_b | self.ticket_none
        found = self._search_as(
            self.user_none, "helpdesk.ticket", [("id", "in", tickets.ids)]
        )
        self.assertEqual(found.ids, self.ticket_none.ids)

    def test_ticket_report_rule_filters_report(self):
        rule = self.env.ref(
            "alda_helpdesk_pms_enterprise."
            "helpdesk_ticket_report_analysis_property_rule_multi_company"
        )
        self.assertEqual(rule.model_id.model, "helpdesk.ticket.report.analysis")
        self.env.flush_all()
        tickets = self.ticket_a | self.ticket_b | self.ticket_none
        rows = self._search_as(
            self.user_a,
            "helpdesk.ticket.report.analysis",
            [("ticket_id", "in", tickets.ids)],
        )
        self.assertEqual(
            sorted(rows.mapped("ticket_id").ids),
            sorted((self.ticket_a | self.ticket_none).ids),
        )

    def test_sla_report_rule_filters_report(self):
        rule = self.env.ref(
            "alda_helpdesk_pms_enterprise.helpdesk_sla_report_analysis_property_rule"
        )
        self.assertEqual(rule.model_id.model, "helpdesk.sla.report.analysis")
        stage = self.env["helpdesk.stage"].create(
            {"name": "Test Stage", "team_ids": [(4, self.team_internal.id)]}
        )
        sla = self.env["helpdesk.sla"].create(
            {
                "name": "Test SLA",
                "team_id": self.team_internal.id,
                "stage_id": stage.id,
                "time": 1,
            }
        )
        tickets = self.ticket_a | self.ticket_b
        self.env["helpdesk.sla.status"].create(
            [{"ticket_id": ticket.id, "sla_id": sla.id} for ticket in tickets]
        )
        self.env.flush_all()
        rows = self._search_as(
            self.user_a,
            "helpdesk.sla.report.analysis",
            [("ticket_id", "in", tickets.ids)],
        )
        self.assertEqual(rows.mapped("ticket_id").ids, self.ticket_a.ids)
        rows = self._search_as(
            self.creator,
            "helpdesk.sla.report.analysis",
            [("ticket_id", "in", tickets.ids)],
        )
        self.assertEqual(sorted(rows.mapped("ticket_id").ids), sorted(tickets.ids))
