from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.pms_ai_tool.tools import PARAM_ENVIRONMENT, PARAM_WRITE_ENABLED

CUSTOMER_EMAIL = "carmen.customer@example.com"
CUSTOMER_PHONE = "+34 611 222 333"
DESCRIPTION = (
    "<p>La lavadora no centrifuga.</p>"
    "<p>Llamar al 600111222 o escribir a carmen@example.com</p>"
)
WRITE_TOOLS = ("alda_helpdesk_ticket_add_note", "alda_helpdesk_activity_schedule")


@tagged("post_install", "-at_install")
class HelpdeskToolsCase(TransactionCase):
    """Tickets of two hotels and two teams, and the users that see them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param(PARAM_ENVIRONMENT, "test")
        params.set_param(PARAM_WRITE_ENABLED, "True")
        # Whatever the demo data of the helpdesk brings does not take part.
        cls.env["helpdesk.ticket"].search([]).write({"active": False})
        cls._setup_properties()
        cls._setup_users()
        cls._setup_helpdesk()
        cls._setup_tickets()
        for name in WRITE_TOOLS:
            cls.env.ref(f"alda_ai_tool_helpdesk.ai_tool_{name}").write(
                {
                    "allowed_user_ids": [(6, 0, (cls.agent | cls.stranger).ids)],
                    "write_enabled": True,
                }
            )
        cls.env.invalidate_all()

    @classmethod
    def _setup_properties(cls):
        plan = cls.env["pms.availability.plan"].create({"name": "AI plan"})
        pricelist = cls.env["product.pricelist"].create(
            {
                "name": "AI pricelist",
                "availability_plan_id": plan.id,
                "is_pms_available": True,
            }
        )
        cls.prop_a, cls.prop_b = cls.env["pms.property"].create(
            [
                {
                    "name": name,
                    "company_id": cls.env.company.id,
                    "default_pricelist_id": pricelist.id,
                }
                for name in ("AI hotel A", "AI hotel B")
            ]
        )

    @classmethod
    def _setup_users(cls):
        groups = "base.group_user,helpdesk.group_helpdesk_user,pms.group_pms_user"

        def user(login, name, prop, **vals):
            return new_test_user(
                cls.env,
                login=login,
                name=name,
                groups=groups,
                pms_property_ids=[(6, 0, prop.ids)],
                pms_property_id=prop.id,
                **vals,
            )

        cls.agent = user("ai_hd_agent", "Agent Alda", cls.prop_a, tz="Europe/Madrid")
        cls.colleague = user("ai_hd_colleague", "Colleague Alda", cls.prop_a)
        cls.stranger = user("ai_hd_stranger", "Stranger Alda", cls.prop_b)
        # An employee without access to the helpdesk, a customer of the portal
        # and someone who left.
        cls.plain = new_test_user(
            cls.env, login="ai_hd_plain", name="Plain Alda", groups="base.group_user"
        )
        cls.portal = new_test_user(
            cls.env,
            login="ai_hd_portal",
            name="Portal Alda",
            groups="base.group_portal",
        )
        cls.archived = user("ai_hd_archived", "Archived Alda", cls.prop_a)
        cls.archived.active = False

    @classmethod
    def _setup_helpdesk(cls):
        Stage = cls.env["helpdesk.stage"]
        cls.stage_new = Stage.create({"name": "AI New", "sequence": 0})
        cls.stage_progress = Stage.create({"name": "AI Progress", "sequence": 1})
        cls.stage_solved = Stage.create(
            {"name": "AI Solved", "sequence": 2, "fold": True}
        )
        members = (cls.agent | cls.colleague | cls.stranger).ids
        stages = cls.stage_new | cls.stage_progress | cls.stage_solved
        Team = cls.env["helpdesk.team"]
        cls.team = Team.create(
            {
                "name": "AI team",
                "use_sla": True,
                "stage_ids": [(6, 0, stages.ids)],
                "member_ids": [(6, 0, members)],
            }
        )
        cls.team2 = Team.create(
            {
                "name": "AI other team",
                "stage_ids": [(6, 0, (cls.stage_new | cls.stage_solved).ids)],
                "member_ids": [(6, 0, members)],
            }
        )
        cls.env["helpdesk.sla"].create(
            {
                "name": "AI SLA",
                "team_id": cls.team.id,
                "stage_id": cls.stage_solved.id,
                "time": 8,
            }
        )

    @classmethod
    def _ticket(cls, name, stage, prop, team=None, **vals):
        return (
            cls.env["helpdesk.ticket"]
            .with_context(allowed_pms_property_ids=(cls.prop_a | cls.prop_b).ids)
            .create(
                dict(
                    {
                        "name": name,
                        "team_id": (team or cls.team).id,
                        "stage_id": stage.id,
                        "pms_property_id": prop.id,
                    },
                    **vals,
                )
            )
        )

    @classmethod
    def _setup_tickets(cls):
        customer = cls.env["res.partner"].create(
            {
                "name": "Carmen Customer",
                "email": CUSTOMER_EMAIL,
                "phone": CUSTOMER_PHONE,
            }
        )
        cls.t1 = cls._ticket(
            "Lavadora averiada",
            cls.stage_new,
            cls.prop_a,
            user_id=cls.agent.id,
            partner_id=customer.id,
            description=DESCRIPTION,
        )
        cls.t2 = cls._ticket("Wifi caído en recepción", cls.stage_progress, cls.prop_a)
        cls.t3 = cls._ticket(
            "Calefacción reparada",
            cls.stage_solved,
            cls.prop_a,
            user_id=cls.colleague.id,
        )
        cls.t4 = cls._ticket("Lavadora del otro hotel", cls.stage_new, cls.prop_b)
        cls.t5 = cls._ticket(
            "Pregunta general sin hotel", cls.stage_new, cls.env["pms.property"]
        )
        cls.t6 = cls._ticket(
            "Aire acondicionado", cls.stage_new, cls.prop_a, team=cls.team2
        )
        cls.env.flush_all()
        for ticket, created, updated in (
            (cls.t1, "3 days", "1 day"),
            (cls.t2, "10 days", "5 days"),
            (cls.t3, "20 days", "10 days"),
        ):
            cls.env.cr.execute(
                """UPDATE helpdesk_ticket
                      SET create_date = now() at time zone 'utc' - %s::interval,
                          write_date = now() at time zone 'utc' - %s::interval
                    WHERE id = %s""",
                [created, updated, ticket.id],
            )

    def _run(self, tool, user=None, **kwargs):
        return (
            self.env.ref(f"alda_ai_tool_helpdesk.ai_tool_{tool}")
            .with_user(user or self.agent)
            ._execute_tool(**kwargs)
        )

    def _confirmed(self, tool, **kwargs):
        preview = self._run(tool, **kwargs)
        token = preview["confirmation"]["confirmation_token"]
        applied = self._run(tool, confirm=True, confirmation_token=token, **kwargs)
        return preview, applied
