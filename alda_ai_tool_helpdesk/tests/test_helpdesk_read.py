import json

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from odoo.addons.pms_ai_tool.tools import get_guard

from .common import CUSTOMER_EMAIL, HelpdeskToolsCase


def refs(*tickets):
    return [ticket.ticket_ref for ticket in tickets]


@tagged("post_install", "-at_install")
class TestHelpdeskSearch(HelpdeskToolsCase):
    def _search(self, **kwargs):
        return self._run("alda_helpdesk_ticket_search", **kwargs)

    def _refs(self, response):
        return [row["ticket_ref"] for row in response["result"]["tickets"]]

    def test_default_search_shows_open_tickets_of_the_user(self):
        response = self._search()
        self.assertEqual(response["tool"], "alda_helpdesk_ticket_search")
        self.assertEqual(response["environment"], "test")
        for key in ("generated_at", "summary", "period", "definitions", "warnings"):
            self.assertIn(key, response)
        # Open, from the hotels of the agent and without hotel; the last saved
        # first. Neither the closed one nor the one of the other hotel.
        self.assertEqual(self._refs(response), refs(self.t6, self.t5, self.t1, self.t2))
        self.assertEqual(response["result"]["total"], 4)
        row = {r["ticket_ref"]: r for r in response["result"]["tickets"]}[
            self.t1.ticket_ref
        ]
        self.assertEqual(row["title"], "Lavadora averiada")
        self.assertEqual(row["team"], "AI team")
        self.assertEqual(row["stage"], "AI New")
        self.assertFalse(row["closed"])
        self.assertEqual(row["assignee"], "Agent Alda")
        self.assertEqual(row["property"], "AI hotel A")
        self.assertTrue(row["created"].endswith(("+01:00", "+02:00")))
        self.assertTrue(row["last_update"].endswith(("+01:00", "+02:00")))

    def test_filters(self):
        self.assertEqual(self._refs(self._search(stage_kind="closed")), refs(self.t3))
        self.assertEqual(
            set(self._refs(self._search(stage_kind="all"))),
            set(refs(self.t1, self.t2, self.t3, self.t5, self.t6)),
        )
        self.assertEqual(
            self._refs(self._search(ticket_ref=self.t1.ticket_ref)), refs(self.t1)
        )
        self.assertEqual(
            self._refs(self._search(ticket_ref=f"#{self.t1.ticket_ref}")),
            refs(self.t1),
        )
        self.assertEqual(
            self._refs(self._search(property_id=self.prop_a.id)),
            refs(self.t6, self.t1, self.t2),
        )
        self.assertEqual(self._refs(self._search(team_id=self.team2.id)), refs(self.t6))
        with self.assertRaisesRegex(UserError, "Unknown team"):
            self._search(team_id=999999)

    def test_text_search(self):
        self.assertEqual(self._refs(self._search(text="lavadora")), refs(self.t1))
        # Words of the description count, and every word must appear.
        self.assertEqual(self._refs(self._search(text="centrifuga")), refs(self.t1))
        self.assertEqual(self._refs(self._search(text="WIFI recepci")), refs(self.t2))
        self.assertEqual(self._refs(self._search(text="wifi lavadora")), [])
        # % and _ are searched as themselves, not as wildcards.
        self.assertEqual(self._search(text="%")["result"]["total"], 0)
        self.assertEqual(self._search(text="_")["result"]["total"], 0)

    def test_limit(self):
        response = self._search(limit=2)
        self.assertEqual(len(response["result"]["tickets"]), 2)
        self.assertEqual(response["result"]["total"], 4)
        self.assertTrue(
            any(
                w.startswith("Only the first 2 of 4 tickets")
                for w in response["warnings"]
            )
        )

    def test_scope(self):
        # The other hotel's agent sees its own ticket and the one without hotel.
        response = self._search(user=self.stranger)
        self.assertEqual(
            set(self._refs(response)), {self.t4.ticket_ref, self.t5.ticket_ref}
        )
        self.assertEqual(
            self._refs(self._search(user=self.stranger, text="lavadora")),
            [self.t4.ticket_ref],
        )
        with self.assertRaises(AccessError):
            self._search(property_id=self.prop_b.id)
        with self.assertRaises(AccessError):
            self._run("alda_helpdesk_ticket_search", user=self.plain)

    def test_arguments(self):
        with self.assertRaisesRegex(UserError, "must be one of"):
            self._search(stage_kind="everything")
        with self.assertRaisesRegex(UserError, "longer than"):
            self._search(text="x" * 101)
        with self.assertRaisesRegex(UserError, "Unknown arguments"):
            self._search(domain="[]")
        with self.assertRaisesRegex(UserError, "must be at most"):
            self._search(limit=500)
        with self.assertRaisesRegex(UserError, "must be an integer"):
            self._search(property_id="1")


@tagged("post_install", "-at_install")
class TestHelpdeskDetail(HelpdeskToolsCase):
    def _detail(self, ticket=None, **kwargs):
        kwargs.setdefault("ticket_ref", (ticket or self.t1).ticket_ref)
        return self._run("alda_helpdesk_ticket_detail", **kwargs)

    def _post(self, ticket, body, internal=False, author=None):
        return ticket.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_note" if internal else "mail.mt_comment",
            author_id=(author or self.colleague).partner_id.id,
        )

    def test_ticket_customer_and_texts(self):
        response = self._detail()
        self.assertEqual(response["tool"], "alda_helpdesk_ticket_detail")
        result = response["result"]
        ticket = result["ticket"]
        self.assertEqual(ticket["ticket_ref"], self.t1.ticket_ref)
        self.assertEqual(ticket["title"], "Lavadora averiada")
        self.assertEqual(ticket["team"], "AI team")
        self.assertEqual(ticket["stage"], "AI New")
        self.assertEqual(ticket["assignee"], "Agent Alda")
        self.assertEqual(ticket["priority"], "Low priority")
        self.assertEqual(result["links"]["property"]["name"], "AI hotel A")
        self.assertIsNone(result["links"]["room"])
        self.assertEqual(
            result["customer"],
            {"name": "Carmen Customer", "email": "c***@example.com", "phone": "***333"},
        )
        # Plain text, with the e-mail and the phone of the text masked.
        description = ticket["description"]
        self.assertIn("La lavadora no centrifuga.", description)
        self.assertNotIn("<", description)
        self.assertIn("***222", description)
        self.assertIn("c***@example.com", description)
        dump = json.dumps(response)
        for raw in (CUSTOMER_EMAIL, "carmen@example.com", "600111222", "611 222 333"):
            self.assertNotIn(raw, dump)

    def test_last_ten_messages(self):
        already = self._detail()["result"]["message_count"]
        for number in range(1, 13):
            self._post(self.t1, f"Message {number}", internal=number % 2 == 0)
        self._post(self.t1, "<p>" + "long " * 200 + "</p>", author=self.agent)
        result = self._detail()["result"]
        self.assertEqual(result["message_count"], already + 13)
        messages = result["messages"]
        self.assertEqual(len(messages), 10)
        # Oldest first among the last ten.
        self.assertEqual(
            [m["body"] for m in messages[:-1]], [f"Message {n}" for n in range(4, 13)]
        )
        self.assertEqual(
            [m["internal"] for m in messages[:-1]], [n % 2 == 0 for n in range(4, 13)]
        )
        self.assertEqual(messages[0]["author"], "Colleague Alda")
        self.assertTrue(messages[0]["date"].endswith(("+01:00", "+02:00")))
        last = messages[-1]
        self.assertEqual(last["author"], "Agent Alda")
        self.assertLessEqual(len(last["body"]), 500)
        self.assertTrue(last["body"].endswith("…"))
        self.assertFalse(last["internal"])

    def test_sla_status(self):
        sla = self._detail()["result"]["sla"]
        self.assertTrue(sla["uses_sla"])
        self.assertFalse(sla["failed"])
        (policy,) = sla["policies"]
        self.assertEqual(policy["policy"], "AI SLA")
        self.assertEqual(policy["status"], "ongoing")
        self.assertIsNotNone(policy["deadline"])
        other = self._detail(self.t6)["result"]["sla"]
        self.assertFalse(other["uses_sla"])
        self.assertEqual(other["policies"], [])

    def test_scope_and_arguments(self):
        for kwargs in ({"ticket_ref": "9999"}, {"user": self.stranger}):
            with self.assertRaisesRegex(UserError, "No ticket found"):
                self._detail(**kwargs)
        own = self._detail(self.t4, user=self.stranger)
        self.assertEqual(own["result"]["ticket"]["ticket_ref"], self.t4.ticket_ref)
        with self.assertRaises(AccessError):
            self._detail(user=self.plain)
        with self.assertRaisesRegex(UserError, "Missing arguments"):
            self._run("alda_helpdesk_ticket_detail")
        with self.assertRaisesRegex(UserError, "longer than"):
            self._detail(ticket_ref="1" * 21)
        with self.assertRaisesRegex(UserError, "Unknown arguments"):
            self._detail(ticket_id=self.t1.id)

    def test_personal_data_is_not_logged(self):
        tools = self.env["pms.ai.tools"]
        expected = {
            "_ai_alda_helpdesk_ticket_detail": False,
            "_ai_alda_helpdesk_ticket_search": True,
            "_ai_alda_helpdesk_backlog": True,
        }
        for name, logged in expected.items():
            guard = get_guard(getattr(tools, name))
            self.assertFalse(guard["write"])
            self.assertEqual(guard["log_result"], logged)


@tagged("post_install", "-at_install")
class TestHelpdeskBacklog(HelpdeskToolsCase):
    def _backlog(self, **kwargs):
        return self._run("alda_helpdesk_backlog", **kwargs)

    def test_totals_aging_and_unassigned(self):
        response = self._backlog()
        self.assertEqual(response["tool"], "alda_helpdesk_backlog")
        self.assertTrue(response["definitions"])
        result = response["result"]
        # t1 is 3 days old, t2 10 days old, t5 and t6 new; t3 is closed and t4
        # belongs to the other hotel.
        self.assertEqual(
            result["totals"],
            {
                "open": 4,
                "under_2_days": 2,
                "from_2_to_7_days": 1,
                "over_7_days": 1,
                "unassigned": 3,
            },
        )
        teams = {row["team"]: row for row in result["by_team"]}
        self.assertEqual(teams["AI team"]["open"], 3)
        self.assertEqual(teams["AI team"]["over_7_days"], 1)
        self.assertEqual(teams["AI other team"]["open"], 1)
        rows = {
            (row["team"], row["stage"], row["property"]): row for row in result["rows"]
        }
        self.assertEqual(
            set(rows),
            {
                ("AI team", "AI New", "AI hotel A"),
                ("AI team", "AI Progress", "AI hotel A"),
                ("AI team", "AI New", None),
                ("AI other team", "AI New", "AI hotel A"),
            },
        )
        old = rows[("AI team", "AI Progress", "AI hotel A")]
        self.assertEqual(
            (old["open"], old["over_7_days"], old["unassigned"]), (1, 1, 1)
        )
        mid = rows[("AI team", "AI New", "AI hotel A")]
        self.assertEqual(
            (mid["open"], mid["from_2_to_7_days"], mid["unassigned"]), (1, 1, 0)
        )
        self.assertEqual(mid["property_id"], self.prop_a.id)

    def test_filters(self):
        by_property = self._backlog(property_id=self.prop_a.id)["result"]["totals"]
        self.assertEqual((by_property["open"], by_property["unassigned"]), (3, 2))
        by_team = self._backlog(team_id=self.team2.id)["result"]["totals"]
        self.assertEqual((by_team["open"], by_team["under_2_days"]), (1, 1))
        with self.assertRaisesRegex(UserError, "Unknown team"):
            self._backlog(team_id=999999)

    def test_scope(self):
        totals = self._backlog(user=self.stranger)["result"]["totals"]
        self.assertEqual(totals["open"], 2)
        with self.assertRaises(AccessError):
            self._backlog(property_id=self.prop_b.id)
        with self.assertRaises(AccessError):
            self._backlog(user=self.plain)

    def test_rows_are_limited(self):
        self.env["ir.config_parameter"].sudo().set_param("pms_ai_tool.max_rows", "2")
        response = self._backlog()
        self.assertEqual(len(response["result"]["rows"]), 2)
        self.assertEqual(response["result"]["totals"]["open"], 4)
        self.assertIn("Only the first 2 of 4 rows are shown.", response["warnings"])
