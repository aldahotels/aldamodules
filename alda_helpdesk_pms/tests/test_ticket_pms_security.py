from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import AldaHelpdeskPmsCase

KPI_SPEC = {
    "pms_property_id": "1",
    "occupancy_rate": "",
    "blocked_rooms": "",
    "occupancy_kpi_info": "",
    "block_kpi_info": "",
    "property_count_tickets": "",
}


@tagged("post_install", "-at_install")
class TestTicketPmsSecurity(AldaHelpdeskPmsCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ticket_b = cls._create_ticket(cls.property_b)
        cls.ticket_room_1 = cls._create_ticket(
            cls.property_a, pms_room_id=cls.room_a.id, location_type="room"
        )
        cls.ticket_room_2 = cls._create_ticket(
            cls.property_a, pms_room_id=cls.room_a.id, location_type="room"
        )
        cls.update_action = cls.env.ref("alda_helpdesk_pms.action_update_blocked_rooms")

    def _make_stale(self, tickets):
        # The room has no out-of-service reservation, so the stored value
        # is stale until the next refresh.
        tickets.write({"is_room_blocked": True})
        self.env.flush_all()
        self.env.invalidate_all()

    # Refresh of the blocked state

    def test_refresh_button_only_refreshes_its_ticket(self):
        self._make_stale(self.ticket_room_1 | self.ticket_room_2)
        self.ticket_room_1.with_user(self.helpdesk_user).action_update_is_room_blocked()
        self.env.invalidate_all()
        self.assertFalse(self.ticket_room_1.is_room_blocked)
        self.assertTrue(self.ticket_room_2.is_room_blocked)

    def test_global_refresh_requires_manager(self):
        self._make_stale(self.ticket_room_1 | self.ticket_room_2)
        with self.assertRaises(AccessError):
            self.env["helpdesk.ticket"].with_user(
                self.helpdesk_user
            ).action_update_is_room_blocked()
        self.env["helpdesk.ticket"].with_user(
            self.helpdesk_manager
        ).action_update_is_room_blocked()
        self.env.invalidate_all()
        self.assertFalse(self.ticket_room_1.is_room_blocked)
        self.assertFalse(self.ticket_room_2.is_room_blocked)

    def test_global_refresh_as_superuser(self):
        self._make_stale(self.ticket_room_1)
        self.env["helpdesk.ticket"].sudo().action_update_is_room_blocked()
        self.env.invalidate_all()
        self.assertFalse(self.ticket_room_1.is_room_blocked)

    def test_refresh_action_and_menu_for_managers_only(self):
        def binding_ids(user):
            bindings = (
                self.env["ir.actions.actions"]
                .with_user(user)
                .get_bindings("helpdesk.ticket")
            )
            return [action["id"] for action in bindings.get("action", [])]

        def visible_menus(user):
            return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

        menu_root = self.env.ref("alda_helpdesk_pms.menu_pms_root")
        menu_update = self.env.ref("alda_helpdesk_pms.menu_update_blocked")
        self.assertNotIn(self.env.ref("base.group_user"), menu_root.groups_id)
        self.assertNotIn(self.update_action.id, binding_ids(self.helpdesk_user))
        self.assertIn(self.update_action.id, binding_ids(self.helpdesk_manager))
        hidden = visible_menus(self.helpdesk_user)
        self.assertNotIn(menu_update.id, hidden)
        self.assertNotIn(menu_root.id, hidden)
        visible = visible_menus(self.helpdesk_manager)
        self.assertIn(menu_update.id, visible)
        self.assertIn(menu_root.id, visible)

    # Detail tags

    def test_detail_tags_read_only_for_helpdesk_users(self):
        Tag = self.env["helpdesk.ticket.detail.tag"]
        tag = Tag.create({"name": "Test tag", "tag_key": "test_tag"})
        self.env.invalidate_all()
        self.assertEqual(tag.with_user(self.helpdesk_user).name, "Test tag")
        with self.assertRaises(AccessError):
            Tag.with_user(self.helpdesk_user).create(
                {"name": "Other tag", "tag_key": "other_tag"}
            )
        with self.assertRaises(AccessError):
            tag.with_user(self.helpdesk_user).write({"name": "Renamed"})
        tag.with_user(self.helpdesk_manager).write({"name": "Renamed"})
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            tag.with_user(self.internal_user).read(["name"])

    def test_detail_tags_still_computed_for_helpdesk_users(self):
        self.env["helpdesk.ticket.detail.tag"].search(
            [("tag_key", "=", "external_company")]
        ).unlink()
        ticket = (
            self.env["helpdesk.ticket"]
            .with_user(self.helpdesk_user)
            .create(
                {
                    "name": "External company ticket",
                    "team_id": self.team.id,
                    "pms_property_id": self.property_a.id,
                    "company_external_id": True,
                }
            )
        )
        self.assertIn("external_company", ticket.tag_detail.mapped("tag_key"))

    # PMS figures computed through onchange()

    def _onchange(self, record, user, pms_property, **values):
        values = dict(values, pms_property_id=pms_property.id)
        return (
            record.with_user(user)
            .onchange(values, "pms_property_id", KPI_SPEC)
            .get("value", {})
        )

    def _assert_no_figures(self, result):
        self.assertFalse(result.get("occupancy_rate"))
        self.assertFalse(result.get("blocked_rooms"))
        self.assertFalse(result.get("occupancy_kpi_info"))
        self.assertFalse(result.get("block_kpi_info"))
        self.assertFalse(result.get("property_count_tickets"))

    def test_onchange_foreign_property_returns_no_figures(self):
        Ticket = self.env["helpdesk.ticket"]
        for user in (self.helpdesk_user, self.internal_user, self.portal_user):
            with self.subTest(user=user.login):
                self._assert_no_figures(self._onchange(Ticket, user, self.property_b))
        # Same through the user's own saved ticket.
        self._assert_no_figures(
            self._onchange(self.ticket_a, self.helpdesk_user, self.property_b)
        )

    def test_onchange_own_property_returns_figures(self):
        result = self._onchange(
            self.env["helpdesk.ticket"], self.helpdesk_user, self.property_a
        )
        self.assertTrue(result.get("occupancy_kpi_info"))
        self.assertTrue(result.get("block_kpi_info"))
        self.assertTrue(result.get("property_count_tickets"))

    def test_pms_values_allowed(self):
        Ticket = self.env["helpdesk.ticket"].with_user(self.helpdesk_user)
        self.assertTrue(
            Ticket.new({"pms_property_id": self.property_a.id})._pms_values_allowed()
        )
        self.assertTrue(
            Ticket.new(
                {"pms_property_id": self.property_a.id, "pms_room_id": self.room_a.id}
            )._pms_values_allowed()
        )
        self.assertFalse(
            Ticket.new({"pms_property_id": self.property_b.id})._pms_values_allowed()
        )
        self.assertFalse(
            Ticket.new(
                {"pms_property_id": self.property_a.id, "pms_room_id": self.room_b.id}
            )._pms_values_allowed()
        )
        # Saved tickets rely on the constraint and the record rules.
        self.assertTrue(
            self.ticket_a.with_user(self.helpdesk_user)._pms_values_allowed()
        )

    # KPI popup

    def test_kpi_popup_from_ticket(self):
        action = self.ticket_a.with_user(self.helpdesk_user).action_view_kpi_ticket()
        self.env.invalidate_all()
        popup = (
            self.env["pms.daily.kpi.show"]
            .with_user(self.helpdesk_user)
            .browse(action["res_id"])
        )
        values = popup.read(["pms_property_id", "occupancy_rate", "adr"])[0]
        self.assertEqual(values["pms_property_id"][0], self.property_a.id)
