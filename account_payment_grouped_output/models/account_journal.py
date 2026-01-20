from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    automatic_group_payments_to_reconcile = fields.Boolean(
        string="Automatic Group Payments to Reconcile",
        help="If enabled, payments made through this journal will be automatically grouped for reconciliation days after of creation.",
        default=False,
    )
    grace_days_to_group_payments = fields.Integer(
        string="Grace Days to Group Payments",
        help="Number of days to wait before grouping payments for reconciliation.",
        default=2,
    )

    @api.model
    def _cron_group_outstanding_payments(self):
        journals = self.search([("automatic_group_payments_to_reconcile", "=", True)])
        for journal in journals:
            try:
                journal._group_outstanding_payments_for_journal()
            except Exception as e:
                # No aborta el cron por un diario con error
                self.env.cr.rollback()
                self.env["ir.logging"].create({
                    "name": "group_outstanding_payments",
                    "type": "server",
                    "dbname": self._cr.dbname,
                    "level": "ERROR",
                    "message": str(e),
                    "path": __name__,
                    "func": "_cron_group_outstanding_payments",
                    "line": 0,
                })

    def _group_outstanding_payments_for_journal(self):
        self.ensure_one()
        # Cuentas de pendientes (company-level fallbacks)
        debit_acc = self.company_id.account_journal_payment_debit_account_id
        credit_acc = self.company_id.account_journal_payment_credit_account_id
        account_ids = [acc.id for acc in (debit_acc, credit_acc) if acc]
        if not account_ids:
            return

        today = fields.Date.context_today(self)
        cutoff = today - timedelta(days=self.grace_days_to_group_payments or 0)

        aml_obj = self.env["account.move.line"]
        domain = [
            ("journal_id", "=", self.id),
            ("payment_id", "!=", False),      # líneas procedentes de pagos
            ("reconciled", "=", False),
            ("account_id", "in", account_ids),
            ("parent_state", "=", "posted"),
            ("date", "=", cutoff),
        ]
        amls = aml_obj.search(domain, order="date,id")
        if not amls:
            return

        # Agrupar por fecha y cuenta (no mezclamos inbound/outbound)
        groups = {}
        for aml in amls:
            key = (aml.date, aml.account_id.id)
            groups.setdefault(key, self.env["account.move.line"])
            groups[key] += aml

        for (gdate, gacc_id), lines in groups.items():
            self._create_grouping_move_for_lines(gdate, lines)

    def _create_grouping_move_for_lines(self, gdate, amls):
        # Construye el asiento: líneas inversas por pago + línea de contrapartida agregada sin partner
        Move = self.env["account.move"]
        vals = {
            "date": gdate,
            "journal_id": self.id,
            "ref": _("Auto grouped payments %s - %s") % (self.name, fields.Date.to_string(gdate)),
            "line_ids": [],
            "pms_property_id": self.pms_property_ids and self.pms_property_ids[0].id or False,
        }

        total_debit = 0.0
        total_credit = 0.0
        reverse_names = []

        for aml in amls:
            amount = abs(aml.balance)
            # Línea inversa en la misma cuenta para poder conciliar individualmente
            if aml.balance > 0:  # original es débito -> creamos un crédito
                debit = 0.0
                credit = amount
            else:                # original es crédito -> creamos un débito
                debit = amount
                credit = 0.0

            line_name = "Reverse:%s" % aml.id
            reverse_names.append(line_name)

            vals["line_ids"].append((0, 0, {
                "name": line_name,
                "account_id": aml.account_id.id,
                "partner_id": aml.partner_id.id or False,  # opcional; ayuda a conciliar
                "debit": debit,
                "credit": credit,
                "currency_id": aml.currency_id.id or False,
                "amount_currency": aml.currency_id and (-aml.amount_currency) or 0.0,
                "date_maturity": aml.date_maturity or aml.date,
            }))

            total_debit += debit
            total_credit += credit

        # Línea de contrapartida agregada en la misma cuenta, sin partner (queda abierta para conciliar con el extracto)
        diff = round(total_debit - total_credit, 2)
        if abs(diff) < 0.00001:
            # Nada que balancear (caso raro). Evitar asiento desbalanceado.
            return

        if diff > 0:  # sobra débito -> añadir crédito
            bal_debit = 0.0
            bal_credit = abs(diff)
        else:         # sobra crédito -> añadir débito
            bal_debit = abs(diff)
            bal_credit = 0.0

        # Misma cuenta de pendientes, sin partner
        vals["line_ids"].append((0, 0, {
            "name": _("Grouped pending %s") % fields.Date.to_string(gdate),
            "account_id": amls[0].account_id.id,
            "partner_id": False,
            "debit": bal_debit,
            "credit": bal_credit,
            "currency_id": amls[0].currency_id.id,
            "amount_currency": -1 * diff,
            "date_maturity": gdate,
        }))

        move = Move.create(vals)
        move.action_post()

        # Conciliar cada pago con su línea inversa; la línea agregada queda abierta
        for aml in amls:
            rev = move.line_ids.filtered(lambda l: l.name == ("Reverse:%s" % aml.id))
            if rev:
                (aml + rev).reconcile()
