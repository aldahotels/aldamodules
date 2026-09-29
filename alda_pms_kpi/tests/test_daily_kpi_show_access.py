from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

KPI_SPEC = {
    "kpi_id": "1",
    "pms_property_id": "",
    "occupancy_rate": "",
    "adr": "",
    "revpar": "",
}


@tagged("post_install", "-at_install")
class TestDailyKpiShowAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.property = cls.env.ref("pms.main_pms_property")
        cls.kpi = cls.env["pms.daily.kpi"].create_or_update_daily_kpi(
            cls.property.id, fields.Date.today()
        )
        user_vals = {
            "company_id": cls.property.company_id.id,
            "company_ids": [(6, 0, cls.property.company_id.ids)],
            "pms_property_ids": [(6, 0, cls.property.ids)],
            "pms_property_id": cls.property.id,
        }
        cls.user = new_test_user(
            cls.env, login="alda_kpi_user", groups="base.group_user"
        )
        cls.other_user = new_test_user(
            cls.env, login="alda_kpi_other", groups="base.group_user"
        )
        cls.pms_user = new_test_user(
            cls.env, login="alda_kpi_pms_user", groups="pms.group_pms_user", **user_vals
        )
        cls.pms_manager = new_test_user(
            cls.env,
            login="alda_kpi_pms_manager",
            groups="pms.group_pms_manager",
            **user_vals,
        )

    def _popup_for(self, user):
        # Same as the ticket button: created with sudo(), owned by the user.
        return (
            self.env["pms.daily.kpi.show"]
            .with_user(user)
            .sudo()
            .create({"kpi_id": self.kpi.id})
        )

    def test_popup_cannot_be_created_by_users(self):
        with self.assertRaises(AccessError):
            self.env["pms.daily.kpi.show"].with_user(self.user).create(
                {"kpi_id": self.kpi.id}
            )

    def test_popup_readable_by_its_owner_only(self):
        popup = self._popup_for(self.user)
        self.env.invalidate_all()
        values = popup.with_user(self.user).read(["adr", "revpar", "occupancy_rate"])
        self.assertEqual(values[0]["id"], popup.id)
        other_popup = self._popup_for(self.other_user)
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            other_popup.with_user(self.user).read(["adr"])

    def test_onchange_requires_kpi_access(self):
        with self.assertRaises(AccessError):
            self.env["pms.daily.kpi.show"].with_user(self.user).onchange(
                {"kpi_id": self.kpi.id}, "kpi_id", KPI_SPEC
            )
        result = (
            self.env["pms.daily.kpi.show"]
            .with_user(self.pms_manager)
            .onchange({"kpi_id": self.kpi.id}, "kpi_id", KPI_SPEC)
        )
        self.assertEqual(result["value"]["pms_property_id"][0], self.property.id)

    def test_property_form_kpi_buttons_for_managers(self):
        def form_arch(user):
            views = (
                self.env["pms.property"].with_user(user).get_views([(False, "form")])
            )
            return views["views"]["form"]["arch"]

        self.assertNotIn('name="kpi_count"', form_arch(self.pms_user))
        self.assertIn('name="kpi_count"', form_arch(self.pms_manager))
