from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase


class AldaHelpdeskPmsCase(TransactionCase):
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
        room_type = cls.env["pms.room.type"].create(
            {
                "name": "Test Room Type",
                "default_code": "ALDA_TST",
                "class_id": cls.env["pms.room.type.class"]
                .create({"name": "Test Room Class", "default_code": "ALDA_TSTC"})
                .id,
            }
        )
        cls.room_a = cls.env["pms.room"].create(
            {
                "name": "Test Room A",
                "pms_property_id": cls.property_a.id,
                "room_type_id": room_type.id,
                "capacity": 2,
            }
        )
        cls.room_b = cls.env["pms.room"].create(
            {
                "name": "Test Room B",
                "pms_property_id": cls.property_b.id,
                "room_type_id": room_type.id,
                "capacity": 2,
            }
        )
        company_vals = {
            "company_id": cls.company.id,
            "company_ids": [(6, 0, cls.company.ids)],
        }
        # The property constraint validates against the env user, so fixture
        # tickets are created by a user who holds both properties.
        cls.creator = new_test_user(
            cls.env,
            login="alda_hdp_creator",
            groups="helpdesk.group_helpdesk_manager,pms.group_pms_user",
            pms_property_ids=[(6, 0, (cls.property_a | cls.property_b).ids)],
            pms_property_id=cls.property_a.id,
            **company_vals,
        )
        cls.helpdesk_user = new_test_user(
            cls.env,
            login="alda_hdp_user",
            groups="helpdesk.group_helpdesk_user,pms.group_pms_user",
            pms_property_ids=[(6, 0, cls.property_a.ids)],
            pms_property_id=cls.property_a.id,
            **company_vals,
        )
        cls.helpdesk_manager = new_test_user(
            cls.env,
            login="alda_hdp_manager",
            groups="helpdesk.group_helpdesk_manager,pms.group_pms_user",
            pms_property_ids=[(6, 0, cls.property_a.ids)],
            pms_property_id=cls.property_a.id,
            **company_vals,
        )
        cls.internal_user = new_test_user(
            cls.env, login="alda_hdp_internal", groups="base.group_user", **company_vals
        )
        cls.portal_user = new_test_user(
            cls.env, login="alda_hdp_portal", groups="base.group_portal"
        )
        cls.team = cls.env["helpdesk.team"].create(
            {
                "name": "Test PMS Team",
                "privacy_visibility": "internal",
                "is_pms_form": True,
                "member_ids": [(6, 0, cls.creator.ids)],
            }
        )
        cls.ticket_a = cls._create_ticket(cls.property_a)

    @classmethod
    def _create_ticket(cls, pms_property, **vals):
        return (
            cls.env["helpdesk.ticket"]
            .with_user(cls.creator)
            .sudo()
            .create(
                dict(
                    {
                        "name": "Test ticket",
                        "team_id": cls.team.id,
                        "user_id": cls.creator.id,
                        "pms_property_id": pms_property.id,
                    },
                    **vals,
                )
            )
        )
