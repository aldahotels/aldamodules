import os
from unittest.mock import patch

from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.pms_ai_tool.tools import PARAM_WRITE_ENABLED

from ..models.lab import PARAM_LAB_ENABLED


class LabCase(TransactionCase):
    """A small hotel, a lab user allowed on every lab tool, and the lab on."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        environment = patch.dict(os.environ, {"DOODBA_ENVIRONMENT": "test"})
        environment.start()
        cls.addClassCleanup(environment.stop)
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param(PARAM_LAB_ENABLED, "True")
        params.set_param(PARAM_WRITE_ENABLED, "True")
        cls.availability_plan = cls.env["pms.availability.plan"].create(
            {"name": "Lab plan"}
        )
        cls.pricelist = cls.env["product.pricelist"].create(
            {
                "name": "Lab pricelist",
                "availability_plan_id": cls.availability_plan.id,
                "is_pms_available": True,
            }
        )
        cls.prop = cls.env["pms.property"].create(
            {
                "name": "Lab hotel",
                "company_id": cls.env.company.id,
                "default_pricelist_id": cls.pricelist.id,
            }
        )
        cls.room_class = cls.env["pms.room.type.class"].create(
            {"name": "Lab class", "default_code": "LBC"}
        )
        cls.room_type = cls.env["pms.room.type"].create(
            {
                "pms_property_ids": [(6, 0, cls.prop.ids)],
                "name": "Lab double",
                "default_code": "LBD",
                "class_id": cls.room_class.id,
                "list_price": 100,
            }
        )
        cls.rooms = cls.env["pms.room"].create(
            [
                {
                    "pms_property_id": cls.prop.id,
                    "name": f"Lab room {n}",
                    "short_name": f"L{n}",
                    "room_type_id": cls.room_type.id,
                    "capacity": 2,
                }
                for n in range(1, 5)
            ]
        )
        cls.direct = cls.env["pms.sale.channel"].create(
            {"name": "Lab door", "channel_type": "direct"}
        )
        cls.company_partner = cls.env["res.partner"].create(
            {"name": "Lab Company", "is_company": True, "email": "lab@example.com"}
        )
        cls.user = new_test_user(
            cls.env,
            login="ai_lab",
            groups="base.group_user,pms.group_pms_user",
            pms_property_ids=[(6, 0, cls.prop.ids)],
            pms_property_id=cls.prop.id,
            tz="Europe/Madrid",
        )
        cls.lab_tools = cls.env["ai.tool"].search(
            [("model_id.model", "=like", "alda.ai.lab.%")]
        )
        cls.lab_tools.write(
            {"allowed_user_ids": [(6, 0, cls.user.ids)], "write_enabled": True}
        )

    @classmethod
    def _tool(cls, name):
        tool = cls.env["ai.tool"].search([("name", "=", name)])
        tool.ensure_one()
        return tool

    # The tool name is positional only: tools have arguments called name.
    def run_tool(self, tool_key, /, user=None, **kwargs):
        tool = self._tool(tool_key).with_user(user or self.user)
        return tool._execute_tool(**kwargs)

    def preview_and_apply(self, tool_key, /, user=None, **kwargs):
        """Preview a write tool, then confirm it with the token."""
        preview = self.run_tool(tool_key, user=user, **kwargs)
        token = preview["confirmation"]["confirmation_token"]
        applied = self.run_tool(
            tool_key, user=user, confirm=True, confirmation_token=token, **kwargs
        )
        return preview, applied
