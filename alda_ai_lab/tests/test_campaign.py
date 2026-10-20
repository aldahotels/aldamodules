from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from .common import LabCase

BODY = (
    "<!-- hidden --><p>Hola, <b>os echamos de menos</b>.</p>"
    '<p t-out="object.name">x</p><img src="https://example.com/pixel.png"/>'
    '<p><a href="javascript:alert(1)">trap</a> <a href="https://example.com">web</a></p>'
)


@tagged("post_install", "-at_install")
class TestCampaign(LabCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user.write(
            {
                "email": "lab.user@example.com",
                "groups_id": [
                    (4, cls.env.ref("mass_mailing.group_mass_mailing_user").id)
                ],
            }
        )
        Partner = cls.env["res.partner"]
        cls.good = Partner.create(
            {"name": "Lab good", "is_company": True, "email": "good@example.com"}
        )
        cls.no_email = Partner.create({"name": "Lab no email", "is_company": True})
        cls.blocked = Partner.create(
            {"name": "Lab blocked", "is_company": True, "email": "blocked@example.com"}
        )
        cls.env["mail.blacklist"].create({"email": "blocked@example.com"})
        cls.twin = Partner.create(
            {"name": "Lab twin", "is_company": True, "email": "good@example.com"}
        )
        cls.archived = Partner.create(
            {
                "name": "Lab archived",
                "is_company": True,
                "email": "archived@example.com",
                "active": False,
            }
        )
        cls.partners = cls.good | cls.no_email | cls.blocked | cls.twin | cls.archived
        cls.args = {
            "date_to": "2026-10-05",
            "salesperson_ids": [cls.user.id],
            "subject": "Volvemos a vernos",
            "body_html": BODY,
        }

    def _rows(self):
        return [
            {"partner_id": p.id, "company": p.name, "salesperson": "Lab salesperson"}
            for p in self.partners
        ]

    def _run(self, confirm_with=None, **overrides):
        args = dict(self.args, **overrides)
        Tools = type(self.env["alda.ai.lab.campaign.tools"])
        with patch.object(Tools, "_lab_cooling_rows", return_value=(self._rows(), [])):
            if confirm_with:
                return self.run_tool(
                    "lab_reactivation_campaign",
                    confirm=True,
                    confirmation_token=confirm_with["confirmation"][
                        "confirmation_token"
                    ],
                    **args,
                )
            return self.run_tool("lab_reactivation_campaign", **args)

    def _lab_mailings(self):
        return self.env["mailing.mailing"].search([("name", "=like", "[LAB]%")])

    def test_preview_lists_recipients_and_creates_nothing(self):
        preview = self._run()
        result = preview["result"]
        self.assertEqual(
            [row["partner_id"] for row in result["recipients"]], self.good.ids
        )
        reasons = {row["partner_id"]: row["reason"] for row in result["excluded"]}
        self.assertEqual(
            reasons,
            {
                self.no_email.id: "no email",
                self.blocked.id: "blacklisted",
                self.twin.id: "email used by another recipient",
                self.archived.id: "archived",
            },
        )
        self.assertIn("os echamos de menos", result["body_text"])
        self.assertFalse(self._lab_mailings())

    def test_apply_creates_a_draft_only(self):
        mails = self.env["mail.mail"].search_count([])
        preview = self._run()
        applied = self._run(confirm_with=preview)
        mailing = self._lab_mailings()
        self.assertEqual(mailing.id, applied["result"]["mailing_id"])
        self.assertEqual(mailing.state, "draft")
        self.assertEqual(mailing.mailing_model_real, "res.partner")
        self.assertEqual(
            self.env["res.partner"].search(mailing._parse_mailing_domain()),
            self.good,
        )
        self.assertIn("o_basic_theme", mailing.body_html)
        for unsafe in ("t-out", "<img", "<!--", "javascript:"):
            self.assertNotIn(unsafe, mailing.body_html)
        self.assertIn("https://example.com", mailing.body_html)
        self.assertEqual(self.env["mail.mail"].search_count([]), mails)

    def test_blacklisting_in_between_is_refused(self):
        preview = self._run()
        self.env["mail.blacklist"].create({"email": "good@example.com"})
        with self.assertRaisesRegex(UserError, "does not match"):
            self._run(confirm_with=preview)
        self.assertFalse(self._lab_mailings())

    def test_refusals(self):
        with self.assertRaisesRegex(UserError, "placeholders"):
            self._run(subject="Hola {{ object.name }}")
        self.user.groups_id -= self.env.ref("mass_mailing.group_mass_mailing_user")
        with self.assertRaisesRegex(AccessError, "Email Marketing"):
            self._run()
