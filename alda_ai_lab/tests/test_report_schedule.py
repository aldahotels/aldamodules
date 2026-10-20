from datetime import datetime

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import new_test_user, tagged

from .common import LabCase

WEEKLY = {
    "tool_name": "pms_discounts_summary",
    "period": "previous_week",
    "frequency": "weekly",
    "weekday": "monday",
    "time": "08:00",
}


@tagged("post_install", "-at_install")
class TestReportSchedule(LabCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.odoobot = cls.env.ref("base.partner_root")
        cls.Schedule = cls.env["alda.ai.lab.schedule"]

    def _bot_messages(self, user):
        channels = self.env["mail.channel"].search(
            [
                ("channel_type", "=", "chat"),
                ("channel_member_ids.partner_id", "=", user.partner_id.id),
            ]
        )
        channels = channels.filtered(
            lambda channel: self.odoobot in channel.channel_member_ids.partner_id
        )
        return self.env["mail.message"].search(
            [
                ("model", "=", "mail.channel"),
                ("res_id", "in", channels.ids),
                ("author_id", "=", self.odoobot.id),
            ]
        )

    @freeze_time("2026-10-20 10:00:00")
    def test_schedule_preview_and_send_now(self):
        preview = self.run_tool("lab_report_schedule", send_now=True, **WEEKLY)
        self.assertFalse(self.Schedule.search([]), "the preview creates nothing")
        self.assertFalse(self._bot_messages(self.user))
        applied = self.run_tool(
            "lab_report_schedule",
            send_now=True,
            confirm=True,
            confirmation_token=preview["confirmation"]["confirmation_token"],
            **WEEKLY,
        )
        result = preview["result"]
        self.assertEqual(
            result["arguments_today"],
            {"date_from": "2026-10-12", "date_to": "2026-10-18"},
        )
        # Madrid changes to winter time on 25 October: still 08:00 local.
        self.assertEqual(
            result["next_runs"],
            ["Mon 2026-10-26 08:00", "Mon 2026-11-02 08:00", "Mon 2026-11-09 08:00"],
        )
        self.assertIn("totals", result["sample"]["result"])
        schedule = self.Schedule.browse(applied["result"]["schedule"]["schedule_id"])
        self.assertEqual(schedule.next_run, datetime(2026, 10, 26, 7, 0))
        self.assertEqual(schedule.user_id, self.user)
        self.assertTrue(applied["result"]["sent_now"])
        self.assertEqual(schedule.last_state, "ok")
        (message,) = self._bot_messages(self.user)
        self.assertIn("pms_discounts_summary", message.body)
        self.assertIn("<table", message.body)
        self.assertTrue(self.env.ref("alda_ai_lab.ir_cron_lab_dispatch").active)

    def test_dispatch_keeps_local_time_across_dst(self):
        with freeze_time("2026-10-19 05:00:00"):
            _preview, applied = self.preview_and_apply("lab_report_schedule", **WEEKLY)
        schedule = self.Schedule.browse(applied["result"]["schedule"]["schedule_id"])
        # Monday 19th, 08:00 summer time.
        self.assertEqual(schedule.next_run, datetime(2026, 10, 19, 6, 0))
        self.assertFalse(self._bot_messages(self.user))
        with freeze_time("2026-10-19 06:02:00"):
            self.Schedule._lab_dispatch()
        self.assertEqual(schedule.run_count, 1)
        self.assertEqual(len(self._bot_messages(self.user)), 1)
        # Monday 26th, 08:00 winter time.
        self.assertEqual(schedule.next_run, datetime(2026, 10, 26, 7, 0))
        with freeze_time("2026-10-20 06:02:00"):
            self.Schedule._lab_dispatch()
        self.assertEqual(schedule.run_count, 1, "not due yet")

    @freeze_time("2026-10-20 10:00:00")
    def test_manage_pause_update_cancel(self):
        _preview, applied = self.preview_and_apply("lab_report_schedule", **WEEKLY)
        schedule_id = applied["result"]["schedule"]["schedule_id"]
        schedule = self.Schedule.browse(schedule_id)
        self.preview_and_apply(
            "lab_report_schedule_manage", schedule_id=schedule_id, action="pause"
        )
        self.assertEqual(schedule.state, "paused")
        schedule.next_run = datetime(2026, 10, 20, 9, 0)
        self.Schedule._lab_dispatch()
        self.assertEqual(schedule.run_count, 0, "paused reports do not run")
        self.preview_and_apply(
            "lab_report_schedule_manage", schedule_id=schedule_id, action="resume"
        )
        preview, _applied = self.preview_and_apply(
            "lab_report_schedule_manage",
            schedule_id=schedule_id,
            action="update",
            time="09:30",
            weekday="friday",
        )
        self.assertEqual(
            preview["result"]["changes"]["next_runs"][0], "Fri 2026-10-23 09:30"
        )
        self.assertEqual(schedule.time_of_day, 9.5)
        self.assertEqual(schedule.next_run, datetime(2026, 10, 23, 7, 30))
        self.assertIn("Friday 09:30", schedule.name)
        listed = self.run_tool("lab_report_schedules")["result"]["schedules"]
        self.assertEqual([row["schedule_id"] for row in listed], [schedule_id])
        self.preview_and_apply(
            "lab_report_schedule_manage", schedule_id=schedule_id, action="cancel"
        )
        self.assertEqual(schedule.state, "cancelled")
        self.assertFalse(self.run_tool("lab_report_schedules")["result"]["schedules"])

    @freeze_time("2026-10-20 10:00:00")
    def test_failed_report_is_reported_and_moves_on(self):
        _preview, applied = self.preview_and_apply("lab_report_schedule", **WEEKLY)
        schedule = self.Schedule.browse(applied["result"]["schedule"]["schedule_id"])
        other = new_test_user(self.env, login="ai_lab_other")
        # The owner loses access to the catalogue tool.
        self.env.ref(
            "pms_ai_tool.ai_tool_pms_discounts_summary"
        ).allowed_user_ids = other
        schedule.next_run = datetime(2026, 10, 20, 9, 0)
        self.Schedule._lab_dispatch()
        self.assertEqual(schedule.last_state, "error")
        self.assertIn("not allowed", schedule.last_error)
        (message,) = self._bot_messages(self.user)
        self.assertIn("could not be prepared", message.body)
        self.assertEqual(schedule.next_run, datetime(2026, 10, 26, 7, 0))

    def test_refusals(self):
        with self.assertRaisesRegex(UserError, "Only read tools"):
            self.run_tool(
                "lab_report_schedule",
                **dict(WEEKLY, tool_name="lab_report_schedule_manage"),
            )
        with self.assertRaisesRegex(UserError, "no tool called"):
            self.run_tool("lab_report_schedule", **dict(WEEKLY, tool_name="nope"))
        with self.assertRaisesRegex(UserError, "day of the week"):
            self.run_tool("lab_report_schedule", **dict(WEEKLY, weekday=None))
        with self.assertRaisesRegex(UserError, "invalid format"):
            self.run_tool("lab_report_schedule", **dict(WEEKLY, time="8:00"))
        other = new_test_user(self.env, login="ai_lab_colleague")
        with self.assertRaisesRegex(AccessError, "Only administrators"):
            self.run_tool("lab_report_schedule", recipient_user_ids=other.ids, **WEEKLY)
