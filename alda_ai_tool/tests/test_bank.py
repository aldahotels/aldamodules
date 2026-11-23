from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.pms_ai_tool.tools import PARAM_WRITE_ENABLED


@tagged("post_install", "-at_install")
class TestBankTools(TransactionCase):
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
        analytic_plan = cls.env["account.analytic.plan"].create({"name": "AI hotels"})
        cls.analytic = cls.env["account.analytic.account"].create(
            {"name": "AI hotel 999", "plan_id": analytic_plan.id}
        )
        cls.prop = cls.env["pms.property"].create(
            {
                "name": "AI bank hotel",
                "company_id": company.id,
                "default_pricelist_id": pricelist.id,
                "analytic_account_id": cls.analytic.id,
            }
        )
        Journal = cls.env["account.journal"]
        cls.cb = Journal.create(
            {
                "name": "AI CaixaBank 999",
                "code": "CB999",
                "type": "bank",
                "pms_property_ids": [(6, 0, cls.prop.ids)],
            }
        )
        cls.tb = Journal.create(
            {
                "name": "AI TPV CaixaBank 999",
                "code": "TB999",
                "type": "bank",
                "pms_property_ids": [(6, 0, cls.prop.ids)],
            }
        )
        cls.transit = company.account_journal_payment_debit_account_id
        Account = cls.env["account.account"]
        cls.income = Account.create(
            {
                "code": "70500000099",
                "name": "AI income",
                "account_type": "income",
                "company_id": company.id,
            }
        )
        for code, kind in (("67800000000", "expense"), ("77800000000", "income")):
            if not Account.search(
                [("code", "=", code), ("company_id", "=", company.id)]
            ):
                Account.create(
                    {
                        "code": code,
                        "name": f"AI {code}",
                        "account_type": kind,
                        "company_id": company.id,
                    }
                )
        cls.customer = cls.env["res.partner"].create({"name": "AI customer"})
        # Grouped TPV entries: the open net line of each day.
        cls.tpv_day1 = cls._grouped("2026-09-21", 150.0)
        cls.tpv_day2 = cls._grouped("2026-09-22", 80.0)
        # Transfer collections registered in the bank journal.
        cls.pay_100 = cls._payment("2026-09-22", 100.0)
        cls.pay_200 = cls._payment("2026-09-23", 200.0)
        cls.pay_999 = cls._payment("2026-09-23", 999.0)
        StLine = cls.env["account.bank.statement.line"]

        def st_line(day, concept, amount):
            return StLine.create(
                {
                    "journal_id": cls.cb.id,
                    "date": day,
                    "payment_ref": concept,
                    "amount": amount,
                }
            )

        cls.st_tpv = st_line("2026-09-22", "ON 351145677 2109", 150.0)
        cls.st_cents = st_line("2026-09-23", "ON 351145677 2209", 80.03)
        cls.st_transfer = st_line("2026-09-22", "HBD 12345 VARIAS RESERVAS", 300.0)
        cls.st_missing = st_line("2026-09-24", "TRANSFERENCIA CLIENTE", 75.0)
        cls.st_out = st_line("2026-09-22", "C. 351145677 2109", -9.4)
        # TPV payments of the 25th not grouped yet, and a settlement whose
        # grouped entry is dated the day before the settled day.
        cls.tpv_pay_60 = cls._payment("2026-09-25", 60.0, cls.tb)
        cls.tpv_pay_40 = cls._payment("2026-09-25", 40.0, cls.tb)
        cls.st_pending = st_line("2026-09-26", "ON 351145677 2509", 100.0)
        cls.tpv_day27 = cls._grouped("2026-09-27", 55.0)
        cls.st_other_day = st_line("2026-09-29", "ON 351145677 2809", 55.0)
        cls.taz_user = new_test_user(cls.env, login="ai_taz", name="AI TAZ")
        job = cls.env["hr.job"].create({"name": "TAZ - Técnico administrativo de zona"})
        cls.env["hr.employee"].create(
            {
                "name": "AI TAZ",
                "job_id": job.id,
                "user_id": cls.taz_user.id,
                "property_ids": [(6, 0, cls.prop.ids)],
            }
        )
        cls.user = new_test_user(
            cls.env,
            login="ai_manuel",
            groups="base.group_user,account.group_account_manager,"
            "pms.group_pms_user",
            pms_property_ids=[(6, 0, cls.prop.ids)],
            pms_property_id=cls.prop.id,
        )
        for name in (
            "alda_bank_notify_taz",
            "alda_bank_reconcile",
            "alda_bank_reconcile_all",
        ):
            cls.env.ref(f"alda_ai_tool.ai_tool_{name}").write(
                {"allowed_user_ids": [(6, 0, cls.user.ids)], "write_enabled": True}
            )
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_WRITE_ENABLED, "True")

    @classmethod
    def _grouped(cls, day, amount):
        move = cls.env["account.move"].create(
            {
                "journal_id": cls.tb.id,
                "date": day,
                "ref": f"Pagos agrupados automáticamente TPV - {day}",
                "line_ids": [
                    (0, 0, {"account_id": cls.transit.id, "debit": amount}),
                    (0, 0, {"account_id": cls.income.id, "credit": amount}),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == cls.transit)

    @classmethod
    def _payment(cls, day, amount, journal=None):
        payment = cls.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": cls.customer.id,
                "amount": amount,
                "date": day,
                "journal_id": (journal or cls.cb).id,
            }
        )
        payment.action_post()
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id == cls.transit
        )

    def _run(self, name, **kwargs):
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

    def test_pending_lines(self):
        result = self._run(
            "alda_bank_pending_lines",
            property_id=self.prop.id,
            date_from="2026-09-20",
            date_to="2026-09-30",
        )["result"]
        self.assertEqual(result["hotel_code"], "999")
        self.assertEqual(result["totals"]["tpv"]["lines"], 4)
        self.assertEqual(result["totals"]["transfer"]["lines"], 2)
        self.assertEqual(result["totals"]["outgoing"]["lines"], 1)
        tpv = [row for row in result["lines"] if row["kind"] == "tpv"]
        self.assertEqual(
            [row["settled_date"] for row in tpv],
            ["2026-09-21", "2026-09-22", "2026-09-25", "2026-09-28"],
        )

    def test_match_candidates(self):
        rows = {
            row["statement_line_id"]: row
            for row in self._run(
                "alda_bank_match_candidates",
                statement_line_ids=[
                    self.st_tpv.id,
                    self.st_cents.id,
                    self.st_transfer.id,
                    self.st_missing.id,
                ],
            )["result"]["lines"]
        }
        exact = rows[self.st_tpv.id]["exact_matches"]
        self.assertEqual([c["move_line_id"] for c in exact], self.tpv_day1.ids)
        cents = rows[self.st_cents.id]
        self.assertEqual(cents["difference"], 0.03)
        self.assertEqual(cents["cents_writeoff"]["account"][:11], "77800000000")
        self.assertEqual(
            cents["cents_writeoff"]["analytic_account_id"],
            self.prop.analytic_account_id.id,
        )
        self.assertFalse(cents["notice"])
        (combination,) = rows[self.st_transfer.id]["combinations"]
        self.assertEqual(
            sorted(c["move_line_id"] for c in combination),
            sorted((self.pay_100 | self.pay_200).ids),
        )
        notice = rows[self.st_missing.id]["notice"]
        self.assertEqual(notice["bank_amount"], 75.0)
        self.assertIn("missing", notice["likely_cause"])

    def test_tpv_grouping_pending_and_other_day(self):
        rows = {
            row["statement_line_id"]: row
            for row in self._run(
                "alda_bank_match_candidates",
                statement_line_ids=[self.st_pending.id, self.st_other_day.id],
            )["result"]["lines"]
        }
        pending = rows[self.st_pending.id]
        self.assertTrue(pending["grouping_pending"])
        self.assertEqual(pending["breakdown"]["net"], 100.0)
        self.assertFalse(pending["notice"])
        self.assertFalse(pending["cents_writeoff"])
        other_day = rows[self.st_other_day.id]
        (match,) = other_day["exact_matches"]
        self.assertEqual(match["move_line_id"], self.tpv_day27.id)
        self.assertTrue(match["other_day"])
        self.assertFalse(other_day["notice"])

    def test_notify_taz(self):
        preview, applied = self._confirmed(
            "alda_bank_notify_taz",
            statement_line_id=self.st_missing.id,
            message="Falta un cobro de 75,00 EUR del 24/09.",
        )
        self.assertEqual(
            [r["user_id"] for r in preview["result"]["recipients"]], self.taz_user.ids
        )
        activity = self.env["mail.activity"].browse(applied["result"]["activity_ids"])
        self.assertEqual(activity.user_id, self.taz_user)
        self.assertEqual(activity.res_model, "account.move")
        self.assertEqual(activity.res_id, self.st_missing.move_id.id)
        self.assertIn("75,00", activity.note)
        # The TAZ already has it: no second notice for the same line.
        with self.assertRaisesRegex(UserError, "already have an open activity"):
            self._run(
                "alda_bank_notify_taz",
                statement_line_id=self.st_missing.id,
                message="Falta un cobro de 75,00 EUR del 24/09.",
            )

    def test_reconcile_exact_and_combination(self):
        self._confirmed(
            "alda_bank_reconcile",
            statement_line_id=self.st_tpv.id,
            move_line_ids=self.tpv_day1.ids,
        )
        self.assertTrue(self.st_tpv.is_reconciled)
        self.assertTrue(self.tpv_day1.reconciled)
        self._confirmed(
            "alda_bank_reconcile",
            statement_line_id=self.st_transfer.id,
            move_line_ids=(self.pay_100 | self.pay_200).ids,
        )
        self.assertTrue(self.st_transfer.is_reconciled)

    def test_reconcile_with_cents_writeoff(self):
        preview, applied = self._confirmed(
            "alda_bank_reconcile",
            statement_line_id=self.st_cents.id,
            move_line_ids=self.tpv_day2.ids,
        )
        self.assertEqual(preview["result"]["writeoff"]["amount"], 0.03)
        self.assertTrue(self.st_cents.is_reconciled)
        writeoff = self.st_cents.move_id.line_ids.filtered(
            lambda line: line.account_id.code == "77800000000"
        )
        self.assertEqual(writeoff.credit, 0.03)
        self.assertEqual(
            writeoff.analytic_distribution,
            {str(self.prop.analytic_account_id.id): 100},
        )

    def test_reconcile_refuses_bad_matches(self):
        with self.assertRaisesRegex(UserError, "cannot be"):
            self._run(
                "alda_bank_reconcile",
                statement_line_id=self.st_missing.id,
                move_line_ids=self.pay_999.ids,
            )
        # A TPV settlement is not reconciled with the payments it groups.
        with self.assertRaisesRegex(UserError, "cannot be matched"):
            self._run(
                "alda_bank_reconcile",
                statement_line_id=self.st_pending.id,
                move_line_ids=(self.tpv_pay_60 | self.tpv_pay_40).ids,
            )
        # Nor a transfer with the TPV grouped entry.
        with self.assertRaisesRegex(UserError, "cannot be matched"):
            self._run(
                "alda_bank_reconcile",
                statement_line_id=self.st_transfer.id,
                move_line_ids=self.tpv_day1.ids,
            )
        with self.assertRaisesRegex(UserError, "cannot be matched"):
            self._run(
                "alda_bank_reconcile",
                statement_line_id=self.st_tpv.id,
                move_line_ids=self.st_out.move_id.line_ids[:1].ids,
            )
        self.assertFalse(self.st_missing.is_reconciled)

    # Reconcile everything (CaixaBank)

    def _charges(self):
        """FR journal, a supplier paid at 30 days, bills and bank charges."""
        journal = self.env["account.journal"].create(
            {
                "name": "AI purchases 999",
                "code": "FR999",
                "type": "purchase",
                "pms_property_ids": [(6, 0, self.prop.ids)],
            }
        )
        term = self.env["account.payment.term"].create(
            {
                "name": "AI 30 days",
                "line_ids": [(0, 0, {"value": "balance", "days": 30})],
            }
        )
        supplier = self.env["res.partner"].create(
            {"name": "AI supplier", "property_supplier_payment_term_id": term.id}
        )
        expense = self.env["account.account"].create(
            {
                "code": "62900000099",
                "name": "AI expense",
                "account_type": "expense",
                "company_id": self.env.company.id,
            }
        )

        def bill(day, amount, ref):
            move = self.env["account.move"].create(
                {
                    "move_type": "in_invoice",
                    "journal_id": journal.id,
                    "partner_id": supplier.id,
                    "invoice_date": day,
                    "ref": ref,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "AI supplies",
                                "account_id": expense.id,
                                "price_unit": amount,
                                "tax_ids": [(6, 0, [])],
                            },
                        )
                    ],
                }
            )
            move.action_post()
            return move

        def charge(day, concept, amount):
            return self.env["account.bank.statement.line"].create(
                {
                    "journal_id": self.cb.id,
                    "date": day,
                    "payment_ref": concept,
                    "amount": amount,
                }
            )

        return {
            "late_bill": bill("2026-08-01", 121.0, "AI-A-0001"),
            "late": charge("2026-09-25", "RECIBO PROVEEDOR", -121.0),
            "bill_a": bill("2026-09-01", 50.0, "AI-B-1001"),
            "bill_b": bill("2026-09-02", 50.0, "AI-B-1002"),
            "by_ref": charge("2026-09-21", "TRANSF PROVEEDOR AI-B-1002", -50.0),
            "in_term_bill": bill("2026-09-10", 60.0, "AI-C-0001"),
            "in_term": charge("2026-09-27", "RECIBO PROVEEDOR", -60.0),
            "none": charge("2026-09-28", "COMISION MANTENIMIENTO", -77.77),
        }

    def test_reconcile_all(self):
        charges = self._charges()
        period = {
            "property_id": self.prop.id,
            "date_from": "2026-09-20",
            "date_to": "2026-09-30",
        }
        table = self._run("alda_bank_reconcile_all_preview", **period)["result"][
            "table"
        ]
        self.assertEqual([r["number"] for r in table], list(range(1, len(table) + 1)))
        rows = {row["statement_line_id"]: row for row in table}
        tpv = rows[self.st_tpv.id]
        self.assertEqual(tpv["action"], "reconcile")
        self.assertEqual([c["move_line_id"] for c in tpv["odoo"]], self.tpv_day1.ids)
        self.assertEqual(rows[self.st_other_day.id]["action"], "reconcile")
        # Cents, combinations, pending groupings and notices are not touched.
        for st_line in (
            self.st_cents,
            self.st_transfer,
            self.st_pending,
            self.st_missing,
        ):
            self.assertEqual(rows[st_line.id]["action"], "skip")
        self.assertTrue(rows[self.st_missing.id]["notice"])
        late = rows[charges["late"].id]
        self.assertEqual(late["action"], "reconcile")
        self.assertTrue(late["term"]["late"])
        self.assertEqual(late["term"]["agreed_days"], 30)
        self.assertEqual(late["notice"]["days_since_bill"], 55)
        by_ref = rows[charges["by_ref"].id]
        self.assertEqual(by_ref["action"], "reconcile")
        self.assertEqual(by_ref["candidates"][0]["move_id"], charges["bill_b"].id)
        in_term = rows[charges["in_term"].id]
        self.assertEqual(in_term["action"], "reconcile")
        self.assertFalse(in_term["term"]["late"])
        self.assertFalse(in_term["notice"])
        self.assertEqual(rows[charges["none"].id]["action"], "skip")
        self.assertEqual(rows[self.st_out.id]["action"], "skip")
        # The user leaves the settlement of the 28th out.
        excluded = rows[self.st_other_day.id]["number"]
        preview, applied = self._confirmed(
            "alda_bank_reconcile_all", exclude_numbers=[excluded], **period
        )
        actions = {r["number"]: r["action"] for r in preview["result"]["table"]}
        self.assertEqual(actions[excluded], "excluded")
        self.assertEqual(len(applied["result"]["reconciled"]), 4)
        self.assertFalse(applied["result"]["failed"])
        for st_line in (
            self.st_tpv,
            charges["late"],
            charges["by_ref"],
            charges["in_term"],
        ):
            self.assertTrue(st_line.is_reconciled)
        for st_line in (self.st_other_day, self.st_cents, charges["none"]):
            self.assertFalse(st_line.is_reconciled)
        self.assertIn(charges["late_bill"].payment_state, ("paid", "in_payment"))
        self.assertEqual(charges["bill_a"].payment_state, "not_paid")
        # The late payment, already reconciled, can still be notified.
        _preview, notified = self._confirmed(
            "alda_bank_notify_taz",
            statement_line_id=charges["late"].id,
            message="Factura pagada 55 días después; plazo pactado 30 días.",
        )
        self.assertTrue(notified["result"]["activity_ids"])

    def test_reconcile_all_conflicts_and_writeoffs(self):
        charges = self._charges()
        twin = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.cb.id,
                "date": "2026-09-26",
                "payment_ref": "RECIBO PROVEEDOR",
                "amount": -121.0,
            }
        )
        period = {
            "property_id": self.prop.id,
            "date_from": "2026-09-20",
            "date_to": "2026-09-30",
        }
        preview, applied = self._confirmed(
            "alda_bank_reconcile_all", include_writeoffs=True, **period
        )
        rows = {r["statement_line_id"]: r for r in preview["result"]["table"]}
        # One bill for two bank charges: neither is reconciled.
        for st_line in (charges["late"], twin):
            self.assertEqual(rows[st_line.id]["action"], "skip")
            self.assertFalse(st_line.is_reconciled)
        self.assertEqual(rows[self.st_cents.id]["writeoff"]["amount"], 0.03)
        self.assertTrue(self.st_cents.is_reconciled)
        writeoff = self.st_cents.move_id.line_ids.filtered(
            lambda line: line.account_id.code == "77800000000"
        )
        self.assertEqual(writeoff.credit, 0.03)
        # The cents rule never covers transfers or charges.
        self.assertFalse(self.st_transfer.is_reconciled)

    def test_reconcile_all_needs_a_match(self):
        with self.assertRaisesRegex(UserError, "Nothing to reconcile"):
            self._run(
                "alda_bank_reconcile_all",
                property_id=self.prop.id,
                date_from="2026-09-24",
                date_to="2026-09-24",
            )
        # Without confirmation, nothing is written.
        self._run(
            "alda_bank_reconcile_all",
            property_id=self.prop.id,
            date_from="2026-09-20",
            date_to="2026-09-30",
        )
        self.assertFalse(self.st_tpv.is_reconciled)
