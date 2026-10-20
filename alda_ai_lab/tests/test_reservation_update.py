from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import LabCase


@tagged("post_install", "-at_install")
class TestReservationUpdate(LabCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.start = date.today() + timedelta(days=5)
        cls.other_partner = cls.env["res.partner"].create({"name": "Lab other"})
        cls.res1 = cls._reservation(cls.company_partner, 0, 3)
        cls.res2 = cls._reservation(cls.company_partner, 1, 2)
        cls.cancelled = cls._reservation(cls.company_partner, 0, 2)
        cls.cancelled.action_cancel()
        cls.other = cls._reservation(cls.other_partner, 0, 2)
        cls.args = {
            "date_from": str(cls.start),
            "date_to": str(cls.start + timedelta(days=1)),
            "discount_percent": 10.0,
            "partner_id": cls.company_partner.id,
        }

    @classmethod
    def _reservation(cls, partner, offset, nights):
        checkin = cls.start + timedelta(days=offset)
        return cls.env["pms.reservation"].create(
            {
                "pms_property_id": cls.prop.id,
                "room_type_id": cls.room_type.id,
                "partner_id": partner.id,
                "sale_channel_origin_id": cls.direct.id,
                "checkin": checkin,
                "checkout": checkin + timedelta(days=nights),
            }
        )

    def test_preview_changes_nothing(self):
        before = (self.res1 | self.res2).mapped("price_total")
        preview = self.run_tool("lab_reservations_bulk_update", **self.args)
        result = preview["result"]
        self.assertEqual(
            {row["reservation"] for row in result["changes"]},
            {self.res1.name, self.res2.name},
        )
        # Only the nights inside the window: 2 of res1, 1 of res2.
        nights = {
            row["reservation"]: row["nights_changed"] for row in result["changes"]
        }
        self.assertEqual(nights, {self.res1.name: 2, self.res2.name: 1})
        self.assertEqual(
            result["excluded"],
            [{"reservation": self.cancelled.name, "reason": "its state is cancel"}],
        )
        self.assertEqual((self.res1 | self.res2).mapped("price_total"), before)
        self.assertFalse(
            (self.res1 | self.res2).reservation_line_ids.filtered("discount")
        )

    def test_apply_matches_the_preview(self):
        mails = self.env["mail.mail"].search_count([])
        preview, applied = self.preview_and_apply(
            "lab_reservations_bulk_update", **self.args
        )
        expected = {
            row["reservation"]: row["room_total_after"]
            for row in preview["result"]["changes"]
        }
        for reservation in self.res1 | self.res2:
            self.assertAlmostEqual(
                reservation.price_total, expected[reservation.name], places=2
            )
        window = self.res1.reservation_line_ids.filtered(
            lambda line: line.date <= self.start + timedelta(days=1)
        )
        self.assertEqual(set(window.mapped("discount")), {10.0})
        outside = self.res1.reservation_line_ids - window
        self.assertEqual(set(outside.mapped("discount")), {0.0})
        self.assertFalse(self.other.reservation_line_ids.filtered("discount"))
        self.assertAlmostEqual(
            applied["result"]["impact"],
            preview["result"]["totals"]["impact"],
            places=2,
        )
        self.assertIn("AI lab", self.res1.message_ids[:1].body)
        self.assertEqual(self.env["mail.mail"].search_count([]), mails)

    def test_higher_discounts_are_kept(self):
        line = self.res2.reservation_line_ids.filtered(
            lambda line: line.date == self.start + timedelta(days=1)
        )
        line.discount = 50
        preview, _applied = self.preview_and_apply(
            "lab_reservations_bulk_update", **self.args
        )
        reasons = {
            row["reservation"]: row["reason"] for row in preview["result"]["excluded"]
        }
        self.assertIn("already have this discount", reasons[self.res2.name])
        self.assertEqual(line.discount, 50)

    def test_change_in_between_is_refused(self):
        preview = self.run_tool("lab_reservations_bulk_update", **self.args)
        self.res1.reservation_line_ids[:1].discount = 5
        with self.assertRaisesRegex(UserError, "does not match"):
            self.run_tool(
                "lab_reservations_bulk_update",
                confirm=True,
                confirmation_token=preview["confirmation"]["confirmation_token"],
                **self.args,
            )
        self.assertFalse(self.res2.reservation_line_ids.filtered("discount"))

    def test_refusals(self):
        args = dict(self.args)
        args.pop("partner_id")
        with self.assertRaisesRegex(UserError, "Say which reservations"):
            self.run_tool("lab_reservations_bulk_update", **args)
        with self.assertRaisesRegex(UserError, "start today or later"):
            self.run_tool(
                "lab_reservations_bulk_update",
                **dict(self.args, date_from=str(date.today() - timedelta(days=1))),
            )
        with self.assertRaisesRegex(UserError, "the limit is 1"):
            self.run_tool(
                "lab_reservations_bulk_update", **dict(self.args, max_reservations=1)
            )
