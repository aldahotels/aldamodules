from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.pms_ai_tool.tools import PARAM_WRITE_ENABLED

from ..models.alda_ai_bank_sabadell import PARAM_SABADELL_PREFIX

PROVIDER_CODE = "123456"


@tagged("post_install", "-at_install")
class TestBankSabadell(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        company = cls.env.company
        plan = cls.env["pms.availability.plan"].create({"name": "AI plan"})
        pricelist = cls.env["product.pricelist"].create(
            {
                "name": "AI pricelist",
                "availability_plan_id": plan.id,
                "is_pms_available": True,
            }
        )
        cls.prop = cls.env["pms.property"].create(
            {
                "name": "AI Sabadell hotel",
                "company_id": company.id,
                "default_pricelist_id": pricelist.id,
            }
        )
        Journal = cls.env["account.journal"]

        def journal(code):
            return Journal.create(
                {
                    "name": f"AI journal {code}",
                    "code": code,
                    "type": "bank",
                    "pms_property_ids": [(6, 0, cls.prop.ids)],
                }
            )

        cls.bank = journal("BS998")
        cls.ca = journal("CA998")
        cls.ta = journal("TA998")
        cls.va = journal("VA998")
        cls.wa = journal("WA998")
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_SABADELL_PREFIX, "BS")
        cls.transit = company.account_journal_payment_debit_account_id
        cls.income = cls.env["account.account"].create(
            {
                "code": "70500000098",
                "name": "AI income",
                "account_type": "income",
                "company_id": company.id,
            }
        )
        cls.tools = cls.env["alda.ai.bank.sabadell.tools"]
        # A settlement of 777001 reconciled with the terminal journal before.
        old = cls._st_line("2026-09-10", "POS SETTLEMENT 0000777001", 10.0)
        cls.tools._alda_bank_widget_reconcile(
            old, cls._grouped(cls.ta, "2026-09-09", 10.0)
        )
        cls.va_200 = cls._grouped(cls.va, "2026-10-04", 200.0)
        cls.ta_90 = cls._grouped(cls.ta, "2026-10-04", 90.0)
        cls.ta_refund = cls._grouped(cls.ta, "2026-10-05", -15.0)
        cls.ta_fri = cls._grouped(cls.ta, "2026-10-02", 49.98)
        cls.ta_sat = cls._grouped(cls.ta, "2026-10-03", 70.1)
        customer = cls.env["res.partner"].create({"name": "AI customer"})
        payment = cls.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": customer.id,
                "amount": 120.0,
                "date": "2026-10-05",
                "journal_id": cls.ca.id,
            }
        )
        payment.action_post()
        cls.st_va = cls._st_line(
            "2026-10-05", f"POS SETTLEMENT 000{PROVIDER_CODE}", 200.0
        )
        cls.st_ta = cls._st_line("2026-10-05", "POS SETTLEMENT 0000777001", 90.0)
        cls.st_unknown = cls._st_line("2026-10-05", "POS SETTLEMENT 888002", 45.0)
        cls.st_cash = cls._st_line("2026-10-05", "CASH DEPOSIT 0042", 300.0)
        cls.st_transfer = cls._st_line("2026-10-05", "TRANSFER AI CUSTOMER", 120.0)
        cls.st_refund = cls._st_line("2026-10-06", "POS SETTLEMENT 777001", -15.0)
        # Monday pays Friday and Saturday separately, a few cents off.
        cls.st_sat = cls._st_line(
            "2026-10-05",
            "POS SETTLEMENT 777001",
            70.0,
            "made_on: 2026-10-03\nposting_date: 2026-10-05",
        )
        cls.st_fri = cls._st_line(
            "2026-10-05",
            "POS SETTLEMENT 777001",
            50.0,
            "made_on: 2026-10-02\nposting_date: 2026-10-05",
        )
        cls.user = new_test_user(
            cls.env,
            login="ai_sabadell",
            groups="base.group_user,account.group_account_manager,"
            "pms.group_pms_user",
            pms_property_ids=[(6, 0, cls.prop.ids)],
            pms_property_id=cls.prop.id,
        )
        for name in ("alda_bank_sabadell_merchant", "alda_bank_reconcile_sabadell"):
            cls.env.ref(f"alda_ai_tool.ai_tool_{name}").write(
                {"allowed_user_ids": [(6, 0, cls.user.ids)], "write_enabled": True}
            )
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_WRITE_ENABLED, "True")
        cls.period = {
            "property_id": cls.prop.id,
            "date_from": "2026-10-01",
            "date_to": "2026-10-07",
        }

    @classmethod
    def _st_line(cls, day, concept, amount, notes=None):
        return cls.env["account.bank.statement.line"].create(
            {
                "journal_id": cls.bank.id,
                "date": day,
                "payment_ref": concept,
                "amount": amount,
                "narration": notes,
            }
        )

    @classmethod
    def _grouped(cls, journal, day, amount):
        debit, credit = (amount, 0.0) if amount > 0 else (0.0, -amount)
        move = cls.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": day,
                "ref": f"AI grouped {journal.code} {day}",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": cls.transit.id,
                            "debit": debit,
                            "credit": credit,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": cls.income.id,
                            "debit": credit,
                            "credit": debit,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == cls.transit)

    def _run(self, name, **kwargs):
        with patch.object(
            type(self.tools),
            "_alda_sabadell_provider_codes",
            return_value={PROVIDER_CODE},
        ):
            return (
                self.env.ref(f"alda_ai_tool.ai_tool_{name}")
                .with_user(self.user)
                ._execute_tool(**kwargs)
            )

    def _confirmed(self, name, **kwargs):
        preview = self._run(name, **kwargs)
        token = preview["confirmation"]["confirmation_token"]
        return preview, self._run(
            name, confirm=True, confirmation_token=token, **kwargs
        )

    def _rows(self, result):
        return {row["statement_line_id"]: row for row in result["table"]}

    def test_needs_the_journal_parameter(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_SABADELL_PREFIX, "")
        with self.assertRaisesRegex(UserError, "sabadell_journal_prefix"):
            self._run("alda_bank_sabadell_pending", **self.period)

    def test_pending_and_merchant_types(self):
        result = self._run("alda_bank_sabadell_pending", **self.period)["result"]
        rows = self._rows(result)
        va = rows[self.st_va.id]
        self.assertEqual(va["kind"], "pos")
        self.assertEqual(va["merchant"]["type"], "va")
        self.assertEqual(va["merchant"]["source"], "payment_provider")
        self.assertEqual(va["action"], "reconcile")
        self.assertEqual([c["move_line_id"] for c in va["odoo"]], self.va_200.ids)
        self.assertEqual(va["concept"], f"POS SETTLEMENT 000{PROVIDER_CODE}")
        # Known only from its history: a type to confirm, not reconciled.
        ta = rows[self.st_ta.id]
        self.assertEqual(ta["merchant"]["type"], "ta")
        self.assertTrue(ta["merchant"]["to_confirm"])
        self.assertEqual(ta["action"], "skip")
        self.assertEqual(rows[self.st_unknown.id]["merchant"]["source"], "unknown")
        self.assertEqual(rows[self.st_unknown.id]["action"], "skip")
        self.assertEqual(rows[self.st_cash.id]["kind"], "cash")
        self.assertEqual(rows[self.st_cash.id]["action"], "skip")
        self.assertEqual(rows[self.st_transfer.id]["action"], "reconcile")
        fri = rows[self.st_fri.id]
        self.assertEqual(str(fri["extras"]["made_on"]), "2026-10-02")
        self.assertEqual(str(fri["extras"]["posting_date"]), "2026-10-05")
        merchants = {m["merchant"]: m for m in result["merchants"]}
        self.assertEqual(merchants["777001"]["history"], {"ta": 1})

    def test_confirm_merchant_and_reconcile(self):
        with self.assertRaisesRegex(UserError, "payment provider"):
            self._run(
                "alda_bank_sabadell_merchant",
                property_id=self.prop.id,
                merchant=PROVIDER_CODE,
                journal_type="ta",
            )
        _preview, stored = self._confirmed(
            "alda_bank_sabadell_merchant",
            property_id=self.prop.id,
            merchant="0000777001",
            journal_type="ta",
        )
        merchant = self.env["alda.bank.merchant"].browse(
            stored["result"]["merchant_id"]
        )
        self.assertEqual(merchant.merchant, "777001")
        self.assertEqual(merchant.journal_type, "ta")
        self.assertEqual(merchant.confirmed_by_id, self.user)
        result = self._run("alda_bank_sabadell_pending", **self.period)["result"]
        rows = self._rows(result)
        self.assertEqual(rows[self.st_ta.id]["merchant"]["source"], "confirmed")
        self.assertEqual(rows[self.st_ta.id]["action"], "reconcile")
        refund = rows[self.st_refund.id]
        self.assertEqual(refund["action"], "reconcile")
        self.assertEqual(
            [c["move_line_id"] for c in refund["odoo"]], self.ta_refund.ids
        )
        # Saturday and Friday paid on Monday, a few cents off: paired in
        # chronological order, to confirm, never reconciled.
        fri, sat = rows[self.st_fri.id], rows[self.st_sat.id]
        self.assertEqual(fri["action"], "skip")
        self.assertEqual(fri["order_proposal"]["move_line_id"], self.ta_fri.id)
        self.assertEqual(sat["order_proposal"]["move_line_id"], self.ta_sat.id)
        self.assertTrue(fri["order_proposal"]["to_confirm"])
        self.assertIn("tolerance", fri["reason"])
        self.assertTrue(fri["breakdown"])
        cash = rows[self.st_cash.id]["number"]
        preview, applied = self._confirmed(
            "alda_bank_reconcile_sabadell",
            exclude_numbers=[rows[self.st_transfer.id]["number"]],
            **self.period,
        )
        self.assertEqual(
            {r["number"]: r["action"] for r in preview["result"]["table"]}[cash],
            "skip",
        )
        self.assertEqual(len(applied["result"]["reconciled"]), 3)
        for st_line in (self.st_va, self.st_ta, self.st_refund):
            self.assertTrue(st_line.is_reconciled)
        for st_line in (
            self.st_transfer,
            self.st_cash,
            self.st_unknown,
            self.st_fri,
            self.st_sat,
        ):
            self.assertFalse(st_line.is_reconciled)

    def test_merchant_access(self):
        self.env["alda.bank.merchant"].create(
            {"property_id": self.prop.id, "merchant": "555", "journal_type": "wa"}
        )
        self.assertEqual(
            self.env["alda.bank.merchant"].with_user(self.user).search_count([]), 1
        )
        basic = new_test_user(self.env, login="ai_basic", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.env["alda.bank.merchant"].with_user(basic).search([])
        bookkeeper = new_test_user(
            self.env,
            login="ai_bookkeeper",
            groups="base.group_user,account.group_account_user",
        )
        records = self.env["alda.bank.merchant"].with_user(bookkeeper).search([])
        self.assertEqual(len(records), 1)
        with self.assertRaises(AccessError):
            records.write({"journal_type": "ta"})

    def test_several_journals_of_a_type(self):
        self.env["account.journal"].create(
            {
                "name": "AI second terminal",
                "code": "TA99B",
                "type": "bank",
                "pms_property_ids": [(6, 0, self.prop.ids)],
            }
        )
        with self.assertRaisesRegex(UserError, "several TA journals"):
            self._run(
                "alda_bank_sabadell_merchant",
                property_id=self.prop.id,
                merchant="777001",
                journal_type="ta",
            )
        self._confirmed(
            "alda_bank_sabadell_merchant",
            property_id=self.prop.id,
            merchant="777001",
            journal_type="ta",
            journal_code="TA998",
        )
        merchant = self.env["alda.bank.merchant"].search(
            [("property_id", "=", self.prop.id), ("merchant", "=", "777001")]
        )
        self.assertEqual(merchant.journal_id, self.ta)
        rows = self._rows(
            self._run("alda_bank_sabadell_pending", **self.period)["result"]
        )
        self.assertEqual(rows[self.st_ta.id]["action"], "reconcile")
        self.assertEqual(
            [c["move_line_id"] for c in rows[self.st_ta.id]["odoo"]], self.ta_90.ids
        )

    def test_stored_number_seen_with_another_journal(self):
        merchant = self.env["alda.bank.merchant"].create(
            {
                "property_id": self.prop.id,
                "merchant": "777001",
                "journal_type": "wa",
                "journal_id": self.wa.id,
            }
        )
        # Stored before the settlement of September reconciled with TA.
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE alda_bank_merchant SET write_date = '2026-09-01' WHERE id = %s",
            [merchant.id],
        )
        merchant.invalidate_recordset(["write_date"])
        result = self._run("alda_bank_sabadell_pending", **self.period)
        row = self._rows(result["result"])[self.st_ta.id]
        self.assertEqual(row["action"], "skip")
        self.assertIn("also been reconciled with TA", row["reason"])
        self.assertTrue(any("777001" in w for w in result["warnings"]))
