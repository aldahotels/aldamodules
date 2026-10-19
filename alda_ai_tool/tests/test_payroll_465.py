from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.pms_ai_tool.tools import PARAM_WRITE_ENABLED


@tagged("post_install", "-at_install")
class TestPayroll465(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        company = cls.env.company
        Account = cls.env["account.account"]
        cls.account_465 = Account.create(
            {
                "code": "46500000099",
                "name": "AI payroll 465",
                "account_type": "liability_current",
                "reconcile": True,
                "company_id": company.id,
            }
        )
        cls.expense = Account.create(
            {
                "code": "64000000099",
                "name": "AI salaries",
                "account_type": "expense",
                "company_id": company.id,
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {"name": "AI payroll", "code": "AINO", "type": "general"}
        )
        cls.p1 = cls.env["res.partner"].create({"name": "AI employee 1"})
        cls.p2 = cls.env["res.partner"].create({"name": "AI employee 2"})
        # (date, label, ref, 465 balance, partner)
        rows = [
            ("2026-06-30", "NOM JUN 1111111", "", -100, None),
            ("2026-06-30", "PAGO 1111111", "", 100, None),
            ("2026-07-31", "NOM JUL 2222222", "", -120, None),
            ("2026-08-31", "PAGO 2222222", "", 120, None),
            ("2026-07-31", "NOM JUL 3333333", "", -200, None),
            ("2026-07-31", "PAGO 3333333", "", 150, None),
            ("2026-07-31", "NOM JUL 4444444", "", -80, None),
            ("2026-07-31", "NOM JUL 5555555", "", -50, cls.p1),
            ("2026-07-31", "PAGO 5555555", "", 50, cls.p2),
            ("2026-07-31", "NOMINA SIN NUMERO", "", -30, None),
            ("2026-07-31", "NOM 6666666 7777777", "", -40, None),
            ("2026-07-31", "NOM JUL 8888888", "", -60, None),
            ("2026-07-31", "PAGO", "REF 8888888", 60, None),
        ]
        cls.lines = cls.env["account.move.line"]
        for day, label, ref, balance, partner in rows:
            move = cls.env["account.move"].create(
                {
                    "journal_id": cls.journal.id,
                    "date": day,
                    "ref": ref,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": label,
                                "account_id": cls.account_465.id,
                                "partner_id": partner.id if partner else False,
                                "debit": max(balance, 0),
                                "credit": max(-balance, 0),
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": label,
                                "account_id": cls.expense.id,
                                "debit": max(-balance, 0),
                                "credit": max(balance, 0),
                            },
                        ),
                    ],
                }
            )
            move.action_post()
            cls.lines |= move.line_ids.filtered(
                lambda line: line.account_id == cls.account_465
            )
        cls.user = new_test_user(
            cls.env,
            login="ai_marta",
            groups="base.group_user,account.group_account_manager",
        )
        cls.preview_tool = cls.env.ref("alda_ai_tool.ai_tool_alda_payroll_465_preview")
        cls.reconcile_tool = cls.env.ref(
            "alda_ai_tool.ai_tool_alda_payroll_465_reconcile"
        )
        cls.reconcile_tool.write(
            {"allowed_user_ids": [(6, 0, cls.user.ids)], "write_enabled": True}
        )
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_WRITE_ENABLED, "True")

    def _company_row(self, response):
        (row,) = [
            r
            for r in response["result"]["by_company"]
            if r["company"] == self.env.company.name
        ]
        return row

    def _preview(self):
        return self.preview_tool.with_user(self.user)._execute_tool(
            company_ids=self.env.company.ids
        )

    def _reconcile(self, **kwargs):
        return self.reconcile_tool.with_user(self.user)._execute_tool(
            company_ids=self.env.company.ids, **kwargs
        )

    def test_preview_groups(self):
        response = self._preview()
        row = self._company_row(response)
        self.assertEqual(row["reconcilable_groups"], 3)
        self.assertEqual(row["reconcilable_lines"], 6)
        self.assertEqual(row["reconcilable_amount"], 280.0)
        self.assertEqual(row["mixed_month_groups"], 1)
        self.assertEqual(
            row["pending"],
            {
                "amounts_differ": 1,
                "debit_only": 0,
                "credit_only": 1,
                "partners_differ": 1,
            },
        )
        self.assertEqual(row["no_number_lines"], 1)
        self.assertEqual(row["ambiguous_lines"], 1)
        (mixed,) = response["result"]["mixed_months"]
        self.assertEqual(mixed["number"], "2222222")
        self.assertEqual(mixed["months"], ["2026-07", "2026-08"])
        self.assertEqual(
            {p["number"] for p in response["result"]["pending"]},
            {"3333333", "4444444", "5555555"},
        )
        # No names of employees in the answer.
        self.assertNotIn("AI employee", str(response))

    def test_reconcile_with_confirmation(self):
        preview = self._reconcile()
        self.assertEqual(preview["result"]["groups"], 3)
        self.assertFalse(any(self.lines.mapped("reconciled")))
        token = preview["confirmation"]["confirmation_token"]
        applied = self._reconcile(confirm=True, confirmation_token=token)
        self.assertEqual(applied["result"]["groups"], 3)
        self.assertFalse(applied["result"]["failed"])
        self.lines.invalidate_recordset(["reconciled"])
        reconciled = self.lines.filtered("reconciled")
        self.assertEqual(
            sorted(reconciled.mapped("name")),
            sorted(
                [
                    "NOM JUN 1111111",
                    "PAGO 1111111",
                    "NOM JUL 2222222",
                    "PAGO 2222222",
                    "NOM JUL 8888888",
                    "PAGO",
                ]
            ),
        )
        # A second run has nothing left to reconcile.
        self.assertEqual(self._company_row(self._preview())["reconcilable_groups"], 0)

    def test_reconcile_aborts_when_data_changed(self):
        token = self._reconcile()["confirmation"]["confirmation_token"]
        self.lines.filtered(lambda line: "1111111" in line.name).reconcile()
        with self.assertRaisesRegex(UserError, "does not match"):
            self._reconcile(confirm=True, confirmation_token=token)
        self.lines.invalidate_recordset(["reconciled"])
        self.assertEqual(len(self.lines.filtered("reconciled")), 2)

    def test_max_groups(self):
        preview = self._reconcile(max_groups=1)
        self.assertEqual(preview["result"]["groups"], 1)
        self.assertIn("Only 1 of 3 groups", preview["warnings"][0])
