from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from odoo.addons.pms_ai_tool.tools import get_guard

from .common import HelpdeskToolsCase

NOTE_TOOL = "alda_helpdesk_ticket_add_note"
ACTIVITY_TOOL = "alda_helpdesk_activity_schedule"


@tagged("post_install", "-at_install")
class TestHelpdeskAddNote(HelpdeskToolsCase):
    def _notes(self, ticket=None):
        return self.env["mail.message"].search(
            [
                ("model", "=", "helpdesk.ticket"),
                ("res_id", "=", (ticket or self.t1).id),
                ("subtype_id", "=", self.env.ref("mail.mt_note").id),
            ]
        )

    def _args(self, **kwargs):
        return dict(
            {"ticket_ref": self.t1.ticket_ref, "note": "Called the hotel."}, **kwargs
        )

    def test_preview_then_confirm_posts_one_internal_note(self):
        before = self._notes()
        note = "Called the <b>hotel</b> & agreed a visit."
        preview, applied = self._confirmed(NOTE_TOOL, **self._args(note=f" {note} "))
        self.assertTrue(preview["confirmation"]["required"])
        self.assertEqual(preview["result"]["ticket"]["ticket_ref"], self.t1.ticket_ref)
        self.assertEqual(preview["result"]["ticket"]["title"], "Lavadora averiada")
        self.assertEqual(preview["result"]["note"], note)
        self.assertEqual(preview["result"]["visibility"], "Internal note")
        new = self._notes() - before
        self.assertEqual(len(new), 1)
        self.assertEqual(applied["result"]["message_id"], new.id)
        self.assertEqual(new.message_type, "comment")
        self.assertEqual(new.author_id, self.agent.partner_id)
        # Plain text escaped into HTML, and nobody addressed or notified.
        self.assertIn("&lt;b&gt;hotel&lt;/b&gt; &amp; agreed", new.body)
        self.assertFalse(new.partner_ids)
        self.assertFalse(new.notified_partner_ids)

    def test_preview_changes_nothing(self):
        before = self._notes()
        preview = self._run(NOTE_TOOL, **self._args())
        self.assertIn("confirmation_token", preview["confirmation"])
        self.assertEqual(self._notes(), before)

    def test_wrong_or_used_token_aborts(self):
        before = self._notes()
        args = self._args()
        token = self._run(NOTE_TOOL, **args)["confirmation"]["confirmation_token"]
        with self.assertRaisesRegex(UserError, "does not match"):
            self._run(
                NOTE_TOOL,
                confirm=True,
                confirmation_token=token,
                **self._args(note="Another text."),
            )
        with self.assertRaisesRegex(UserError, "Invalid confirmation_token"):
            self._run(NOTE_TOOL, confirm=True, confirmation_token="garbage", **args)
        with self.assertRaisesRegex(UserError, "Missing confirmation_token"):
            self._run(NOTE_TOOL, confirm=True, **args)
        self.assertEqual(self._notes(), before)
        self._run(NOTE_TOOL, confirm=True, confirmation_token=token, **args)
        self.assertEqual(len(self._notes() - before), 1)
        with self.assertRaisesRegex(UserError, "already used"):
            self._run(NOTE_TOOL, confirm=True, confirmation_token=token, **args)
        self.assertEqual(len(self._notes() - before), 1)

    def test_who_can_use_it(self):
        with self.assertRaisesRegex(AccessError, "not allowed"):
            self._run(NOTE_TOOL, user=self.colleague, **self._args())
        tool = self.env.ref(f"alda_ai_tool_helpdesk.ai_tool_{NOTE_TOOL}")
        tool.write({"write_enabled": False})
        preview = self._run(NOTE_TOOL, **self._args())
        self.assertTrue(any("disabled" in w for w in preview["warnings"]))
        token = preview["confirmation"]["confirmation_token"]
        with self.assertRaisesRegex(UserError, "Changes are disabled"):
            self._run(NOTE_TOOL, confirm=True, confirmation_token=token, **self._args())

    def test_validation_and_scope(self):
        with self.assertRaisesRegex(UserError, "The note is empty"):
            self._run(NOTE_TOOL, **self._args(note="   "))
        with self.assertRaisesRegex(UserError, "longer than"):
            self._run(NOTE_TOOL, **self._args(note="x" * 2001))
        with self.assertRaisesRegex(UserError, "No ticket found"):
            self._run(NOTE_TOOL, **self._args(ticket_ref="9999"))
        # The ticket of the other hotel is not visible to this agent.
        with self.assertRaisesRegex(UserError, "No ticket found"):
            self._run(NOTE_TOOL, **self._args(ticket_ref=self.t4.ticket_ref))
        with self.assertRaisesRegex(UserError, "No ticket found"):
            self._run(NOTE_TOOL, user=self.stranger, **self._args())
        with self.assertRaisesRegex(UserError, "Unknown arguments"):
            self._run(NOTE_TOOL, **self._args(partner_ids=[1]))
        with self.assertRaisesRegex(UserError, "Missing arguments"):
            self._run(NOTE_TOOL, ticket_ref=self.t1.ticket_ref)
        guard = get_guard(getattr(self.env["pms.ai.tools"], "_ai_" + NOTE_TOOL))
        self.assertTrue(guard["write"])


@tagged("post_install", "-at_install")
class TestHelpdeskActivitySchedule(HelpdeskToolsCase):
    def _activities(self, ticket=None):
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", "helpdesk.ticket"),
                ("res_id", "=", (ticket or self.t1).id),
            ]
        )

    def _today(self):
        return fields.Date.context_today(self.env["res.users"].with_user(self.agent))

    def _args(self, **kwargs):
        return dict(
            {
                "ticket_ref": self.t1.ticket_ref,
                "user_id": self.colleague.id,
                "date_deadline": (self._today() + timedelta(days=3)).isoformat(),
                "summary": "Call the hotel back",
                "note": "Ask about the washing machine.",
            },
            **kwargs,
        )

    def test_preview_then_confirm_creates_one_todo(self):
        before = self._activities()
        args = self._args()
        preview, applied = self._confirmed(ACTIVITY_TOOL, **args)
        result = preview["result"]
        self.assertEqual(result["ticket"]["ticket_ref"], self.t1.ticket_ref)
        self.assertEqual(
            result["assignee"], {"user_id": self.colleague.id, "name": "Colleague Alda"}
        )
        self.assertEqual(result["deadline"], args["date_deadline"])
        self.assertEqual(result["summary"], "Call the hotel back")
        self.assertEqual(result["activity_type"], "To-Do")
        self.assertTrue(any("assignment email" in w for w in preview["warnings"]))
        new = self._activities() - before
        self.assertEqual(len(new), 1)
        self.assertEqual(applied["result"]["activity_id"], new.id)
        self.assertEqual(new.user_id, self.colleague)
        self.assertEqual(str(new.date_deadline), args["date_deadline"])
        self.assertEqual(new.summary, "Call the hotel back")
        self.assertEqual(
            new.activity_type_id, self.env.ref("mail.mail_activity_data_todo")
        )
        self.assertIn("washing machine", new.note)
        self.env.invalidate_all()
        self.assertIn(self.colleague.partner_id, self.t1.message_partner_ids)

    def test_note_is_optional_and_preview_changes_nothing(self):
        before = self._activities()
        args = self._args()
        del args["note"]
        preview = self._run(ACTIVITY_TOOL, **args)
        self.assertIsNone(preview["result"]["note"])
        self.assertEqual(self._activities(), before)
        self._confirmed(ACTIVITY_TOOL, **args)
        new = self._activities() - before
        self.assertEqual(len(new), 1)
        self.assertFalse(new.note)

    def test_wrong_token_and_duplicates(self):
        before = self._activities()
        args = self._args()
        token = self._run(ACTIVITY_TOOL, **args)["confirmation"]["confirmation_token"]
        for changed in (
            {"summary": "Something else"},
            {"user_id": self.agent.id},
            {"date_deadline": (self._today() + timedelta(days=4)).isoformat()},
        ):
            with self.assertRaisesRegex(UserError, "does not match"):
                self._run(
                    ACTIVITY_TOOL,
                    confirm=True,
                    confirmation_token=token,
                    **dict(args, **changed),
                )
        self.assertEqual(self._activities(), before)
        self._run(ACTIVITY_TOOL, confirm=True, confirmation_token=token, **args)
        self.assertEqual(len(self._activities() - before), 1)
        # The same user cannot get the same activity twice: neither a new
        # preview nor the replay of the token goes through.
        for extra in ({}, {"confirm": True, "confirmation_token": token}):
            with self.assertRaisesRegex(UserError, "already has an open activity"):
                self._run(ACTIVITY_TOOL, **dict(args, **extra))
        self.assertEqual(len(self._activities() - before), 1)

    def test_deadline_and_texts(self):
        today = self._today()
        with self.assertRaisesRegex(UserError, "cannot be in the past"):
            self._run(
                ACTIVITY_TOOL,
                **self._args(date_deadline=(today - timedelta(days=1)).isoformat()),
            )
        with self.assertRaisesRegex(UserError, "more than 365 days"):
            self._run(
                ACTIVITY_TOOL,
                **self._args(date_deadline=(today + timedelta(days=366)).isoformat()),
            )
        # Today and a year ahead are fine.
        for day in (today, today + timedelta(days=365)):
            self._run(ACTIVITY_TOOL, **self._args(date_deadline=day.isoformat()))
        with self.assertRaisesRegex(UserError, "YYYY-MM-DD"):
            self._run(ACTIVITY_TOOL, **self._args(date_deadline="04/11/2026"))
        with self.assertRaisesRegex(UserError, "The summary is empty"):
            self._run(ACTIVITY_TOOL, **self._args(summary="  "))
        with self.assertRaisesRegex(UserError, "longer than"):
            self._run(ACTIVITY_TOOL, **self._args(summary="x" * 201))
        with self.assertRaisesRegex(UserError, "longer than"):
            self._run(ACTIVITY_TOOL, **self._args(note="x" * 1001))

    def test_assignee_must_be_an_internal_user_who_reads_the_ticket(self):
        # An employee without access to the helpdesk cannot be assigned. Nor
        # can someone archived, a portal user, a user of another hotel (the
        # agent does not see them) or one that does not exist.
        with self.assertRaisesRegex(UserError, "cannot read the ticket"):
            self._run(ACTIVITY_TOOL, **self._args(user_id=self.plain.id))
        for user_id in (
            self.archived.id,
            self.portal.id,
            self.stranger.id,
            999999,
        ):
            with self.assertRaisesRegex(UserError, "not an active internal user"):
                self._run(ACTIVITY_TOOL, **self._args(user_id=user_id))

    def test_scope_and_arguments(self):
        with self.assertRaisesRegex(AccessError, "not allowed"):
            self._run(ACTIVITY_TOOL, user=self.colleague, **self._args())
        for kwargs in (
            {"ticket_ref": "9999"},
            {"ticket_ref": self.t4.ticket_ref},
        ):
            with self.assertRaisesRegex(UserError, "No ticket found"):
                self._run(ACTIVITY_TOOL, **self._args(**kwargs))
        with self.assertRaisesRegex(UserError, "No ticket found"):
            self._run(ACTIVITY_TOOL, user=self.stranger, **self._args())
        with self.assertRaisesRegex(UserError, "Missing arguments"):
            self._run(ACTIVITY_TOOL, ticket_ref=self.t1.ticket_ref)
        with self.assertRaisesRegex(UserError, "Unknown arguments"):
            self._run(ACTIVITY_TOOL, **self._args(activity_type_id=1))
        with self.assertRaisesRegex(UserError, "must be an integer"):
            self._run(ACTIVITY_TOOL, **self._args(user_id="2"))
        guard = get_guard(getattr(self.env["pms.ai.tools"], "_ai_" + ACTIVITY_TOOL))
        self.assertTrue(guard["write"])
