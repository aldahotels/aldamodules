import os
from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from ..models.lab import PARAM_LAB_ENABLED, SMARTLOCK_KEY, lab_silence, lab_silent
from .common import LabCase


@tagged("post_install", "-at_install")
class TestLabGate(LabCase):
    def test_lab_tools_registered(self):
        self.assertEqual(
            set(self.lab_tools.mapped("name")),
            {
                "lab_report_schedule",
                "lab_report_schedules",
                "lab_report_schedule_manage",
                "lab_group_booking_create",
                "lab_reservations_bulk_update",
                "lab_reactivation_campaign",
                "lab_mail_template_create",
            },
        )

    def test_refused_in_production(self):
        tool = self._tool("lab_report_schedules").with_user(self.user)
        self.assertTrue(tool._pms_ai_is_allowed())
        with patch.dict(os.environ, {"DOODBA_ENVIRONMENT": "prod"}):
            self.assertFalse(tool._pms_ai_is_allowed())
            with self.assertRaisesRegex(UserError, "only runs on staging"):
                tool._execute_tool()

    def test_refused_without_the_switch(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_LAB_ENABLED, "False")
        tool = self._tool("lab_report_schedules").with_user(self.user)
        self.assertFalse(tool._pms_ai_is_allowed())
        with self.assertRaisesRegex(UserError, "only runs on staging"):
            tool._execute_tool()

    def test_other_tools_unaffected(self):
        tool = self.env.ref("pms_ai_tool.ai_tool_pms_discounts_summary")
        with patch.dict(os.environ, {"DOODBA_ENVIRONMENT": "prod"}):
            self.assertTrue(tool.with_user(self.user)._pms_ai_is_allowed())


@tagged("post_install", "-at_install")
class TestLabSilence(LabCase):
    def test_refuses_emails(self):
        values = {"subject": "Lab", "email_to": "guest@example.com"}
        with self.assertRaisesRegex(UserError, "create an email"):
            with lab_silence(self.env["mail.mail"]) as mails:
                mails.create(values)
        self.assertFalse(lab_silent())
        # Outside the lab nothing changes.
        self.assertTrue(self.env["mail.mail"].create(values))

    def test_detects_queued_work(self):
        with self.assertRaisesRegex(UserError, r"outside Odoo \(sms.sms\)"):
            with lab_silence(self.env["sms.sms"]) as sms:
                sms.create({"number": "+34600000000", "body": "Lab"})

    def test_staged_door_codes(self):
        reservation = self.env["pms.reservation"].create(
            {
                "pms_property_id": self.prop.id,
                "room_type_id": self.room_type.id,
                "partner_id": self.company_partner.id,
                "sale_channel_origin_id": self.direct.id,
                "checkin": date.today() + timedelta(days=10),
                "checkout": date.today() + timedelta(days=11),
            }
        )
        staged = self.env.cr.precommit.data
        Reservation = type(self.env["pms.reservation"])
        # With the smart lock module, a staged reservation that needs no door
        # code is not a leak.
        with patch.object(
            Reservation, "_should_have_lock_codes", lambda r: False, create=True
        ):
            with lab_silence(reservation) as quiet:
                staged[SMARTLOCK_KEY] = set(quiet.ids)
            self.assertIn(SMARTLOCK_KEY, staged)
            with self.assertRaisesRegex(UserError, "pms_smartlock"):
                with patch.object(
                    Reservation, "_should_have_lock_codes", lambda r: True
                ):
                    with lab_silence(reservation) as quiet:
                        staged[SMARTLOCK_KEY] = set(quiet.ids)
        # Aborting clears what was staged for the commit.
        self.assertNotIn(SMARTLOCK_KEY, staged)

    def test_skips_automated_actions(self):
        self.env["base.automation"].create(
            {
                "name": "Lab mark",
                "model_id": self.env.ref("base.model_res_partner").id,
                "trigger": "on_create",
                "state": "code",
                "code": "record.write({'ref': 'automated'})",
            }
        )
        outside = self.env["res.partner"].create({"name": "Lab outside"})
        self.assertEqual(outside.ref, "automated")
        with lab_silence(self.env["res.partner"]) as partners:
            inside = partners.create({"name": "Lab inside"})
        self.assertFalse(inside.ref)

    def test_refuses_cancelling(self):
        folio = self.env["pms.folio"].create(
            {"pms_property_id": self.prop.id, "partner_name": "Lab guest"}
        )
        with self.assertRaisesRegex(UserError, "cancel a folio"):
            with lab_silence(folio) as quiet:
                quiet.action_cancel()
