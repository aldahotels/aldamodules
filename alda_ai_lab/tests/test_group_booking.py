from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import LabCase


@tagged("post_install", "-at_install")
class TestGroupBooking(LabCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env["product.product"]
        breakfast = Product.create(
            {
                "name": "Lab breakfast",
                "per_day": True,
                "per_person": True,
                "consumed_on": "after",
            }
        )
        dinner = Product.create(
            {
                "name": "Lab dinner",
                "per_day": True,
                "per_person": True,
                "consumed_on": "before",
            }
        )
        cls.board = cls.env["pms.board.service"].create(
            {
                "name": "Lab half board",
                "default_code": "LMP",
                "pms_property_ids": [(6, 0, cls.prop.ids)],
                "board_service_line_ids": [
                    (0, 0, {"product_id": breakfast.id, "amount": 10, "adults": True}),
                    (0, 0, {"product_id": dinner.id, "amount": 20, "adults": True}),
                ],
            }
        )
        cls.env["pms.board.service.room.type"].create(
            {
                "pms_room_type_id": cls.room_type.id,
                "pms_board_service_id": cls.board.id,
                "pms_property_id": cls.prop.id,
            }
        )
        cls.checkin = date.today() + timedelta(days=10)
        cls.args = {
            "property_id": cls.prop.id,
            "checkin": str(cls.checkin),
            "checkout": str(cls.checkin + timedelta(days=2)),
            "rooms": ["LBD=3"],
            "adults": 2,
            "board_service_code": "LMP",
            "partner_id": cls.company_partner.id,
            "sale_channel_id": cls.direct.id,
            "group_name": "Lab congress",
        }

    def _lab_folios(self):
        return self.env["pms.folio"].search([("internal_comment", "=like", "[LAB]%")])

    def test_preview_creates_nothing(self):
        mails = self.env["mail.mail"].search_count([])
        preview = self.run_tool("lab_group_booking_create", **self.args)
        result = preview["result"]
        self.assertTrue(result["can_create"])
        (line,) = result["room_types"]
        self.assertEqual(line["requested"], 3)
        self.assertEqual(len(line["rooms"]), 3)
        self.assertEqual(line["free_whole_stay"], 4)
        self.assertEqual(line["board"], "LMP")
        # 2 adults: breakfast 10 on the 2 mornings, dinner 20 on the 2 nights,
        # plus the sales tax of the test company.
        taxes = (
            self.env["product.product"]
            .search([("name", "=", "Lab breakfast")])
            .taxes_id
        )
        expected = taxes.compute_all(120)["total_included"] if taxes else 120
        self.assertAlmostEqual(line["price_per_room"]["board"], expected, places=2)
        self.assertFalse(self._lab_folios())
        self.assertEqual(self.env["mail.mail"].search_count([]), mails)

    def test_apply_creates_the_group(self):
        mails = self.env["mail.mail"].search_count([])
        preview, applied = self.preview_and_apply(
            "lab_group_booking_create", **self.args
        )
        folio = self._lab_folios()
        self.assertEqual(len(folio), 1)
        self.assertIn("Lab congress", folio.internal_comment)
        self.assertEqual(folio.partner_id, self.company_partner)
        reservations = folio.reservation_ids
        self.assertEqual(len(reservations), 3)
        self.assertEqual(len(set(reservations.mapped("name"))), 3)
        self.assertEqual(
            sorted(reservations.preferred_room_id.mapped("name")),
            sorted(preview["result"]["room_types"][0]["rooms"]),
        )
        self.assertEqual(set(reservations.mapped("state")), {"draft"})
        self.assertTrue(all(reservations.mapped("service_ids")))
        self.assertAlmostEqual(applied["result"]["difference"], 0.0, places=2)
        self.assertAlmostEqual(
            folio.amount_total, preview["result"]["estimated_total"], places=2
        )
        self.assertEqual(self.env["mail.mail"].search_count([]), mails)
        # The token cannot be used twice (the rooms are taken now, too).
        with self.assertRaisesRegex(UserError, "already used|does not match"):
            self.run_tool(
                "lab_group_booking_create",
                confirm=True,
                confirmation_token=preview["confirmation"]["confirmation_token"],
                **self.args,
            )

    def test_room_only(self):
        args = dict(self.args, board_service_code="NONE", rooms=["LBD=1"])
        preview, applied = self.preview_and_apply("lab_group_booking_create", **args)
        reservation = self._lab_folios().reservation_ids
        self.assertFalse(reservation.board_service_room_id)
        self.assertFalse(reservation.service_ids)
        self.assertEqual(preview["result"]["room_types"][0]["board"], None)
        self.assertAlmostEqual(applied["result"]["difference"], 0.0, places=2)

    def test_not_enough_rooms(self):
        args = dict(self.args, rooms=["LBD=5"])
        preview = self.run_tool("lab_group_booking_create", **args)
        self.assertFalse(preview["result"]["can_create"])
        self.assertIn("4 rooms free", preview["result"]["blocking"][0])
        with self.assertRaisesRegex(UserError, "Nothing created"):
            self.run_tool(
                "lab_group_booking_create",
                confirm=True,
                confirmation_token=preview["confirmation"]["confirmation_token"],
                **args,
            )
        self.assertFalse(self._lab_folios())

    def test_booking_in_between_is_refused(self):
        preview = self.run_tool("lab_group_booking_create", **self.args)
        self.env["pms.reservation"].create(
            {
                "pms_property_id": self.prop.id,
                "room_type_id": self.room_type.id,
                "partner_id": self.company_partner.id,
                "sale_channel_origin_id": self.direct.id,
                "checkin": self.checkin,
                "checkout": self.checkin + timedelta(days=1),
            }
        )
        with self.assertRaisesRegex(UserError, "does not match"):
            self.run_tool(
                "lab_group_booking_create",
                confirm=True,
                confirmation_token=preview["confirmation"]["confirmation_token"],
                **self.args,
            )
        self.assertFalse(self._lab_folios())

    def test_refusals(self):
        with self.assertRaisesRegex(UserError, "in 2 days or later"):
            self.run_tool(
                "lab_group_booking_create",
                **dict(self.args, checkin=str(date.today() + timedelta(days=1))),
            )
        with self.assertRaisesRegex(UserError, "Unknown room type XYZ"):
            self.run_tool(
                "lab_group_booking_create", **dict(self.args, rooms=["XYZ=2"])
            )
        with self.assertRaisesRegex(UserError, "has no board"):
            preview = self.run_tool(
                "lab_group_booking_create", **dict(self.args, board_service_code="PC")
            )
            raise UserError(preview["result"]["blocking"][0])
        # An agency needs a PMS pricelist, also the default one.
        self.env["product.pricelist"].search([]).write(
            {
                "is_pms_available": True,
                "availability_plan_id": self.availability_plan.id,
            }
        )
        channel = self.env["pms.sale.channel"].create(
            {"name": "Lab agencies", "channel_type": "indirect"}
        )
        agency = self.env["res.partner"].create(
            {
                "name": "Lab agency",
                "is_company": True,
                "is_agency": True,
                "sale_channel_id": channel.id,
            }
        )
        with self.assertRaisesRegex(UserError, "cannot hold a group"):
            self.run_tool(
                "lab_group_booking_create", **dict(self.args, partner_id=agency.id)
            )
        args = dict(self.args)
        args.pop("partner_id")
        with self.assertRaisesRegex(UserError, "Say who the group is for"):
            self.run_tool("lab_group_booking_create", **args)

    def test_holder_by_name_only(self):
        args = dict(self.args, rooms=["LBD=1"], partner_name="Lab Unknown Group")
        args.pop("partner_id")
        self.preview_and_apply("lab_group_booking_create", **args)
        folio = self._lab_folios()
        self.assertFalse(folio.partner_id)
        self.assertEqual(folio.partner_name, "Lab Unknown Group")
