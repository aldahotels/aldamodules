import logging
import re

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.pms_ai_tool.tools import guarded_tool, truncate

from .alda_ai_bank import CONCEPT_CHARS, PARAM_CENTS, PARAM_PURCHASE_PREFIX, _cents

MAX_ALL_DAYS = 31
MAX_ALL_LINES = 200
MAX_ALL_RECONCILE = 80
MAX_BILL_CANDIDATES = 5
# Supplier references shorter than this are too vague to pick a bill.
MIN_REFERENCE_CHARS = 4

_logger = logging.getLogger(__name__)

ALL_INPUTS = {
    "property_id": {"type": "integer", "description": "Hotel (pms.property)."},
    "date_from": {"type": "string", "format": "date"},
    "date_to": {
        "type": "string",
        "format": "date",
        "description": f"Included, at most {MAX_ALL_DAYS} days after date_from.",
    },
    "include_writeoffs": {
        "type": "boolean",
        "description": "Also reconcile TPV settlements that differ from their "
        "grouped entry by a few cents, writing the difference off (678/778). "
        "False by default: they are listed to review.",
    },
}
ALL_OUTPUT = {
    "hotel_code": {"type": "string"},
    "journals": {"type": "array", "items": {"type": "string"}},
    "totals": {"type": "object"},
    "table": {"type": "array", "items": {"type": "object"}},
    "notices": {"type": "array", "items": {"type": "object"}},
}


def _alnum(text):
    return re.sub(r"[^0-9A-Z]", "", (text or "").upper())


class AldaAiBankTools(models.AbstractModel):
    _inherit = "alda.ai.bank.tools"

    # Charges: vendor bills of the hotel's purchase journal

    @api.model
    def _alda_bank_purchase_journals(self, context):
        prefix = self._alda_bank_param(PARAM_PURCHASE_PREFIX)
        prop = context["property"]
        journals = self.env["account.journal"].search(
            [
                ("type", "=", "purchase"),
                ("company_id", "=", context["company"].id),
                ("code", "=like", f"{prefix}%"),
            ]
        )
        return journals.filtered(
            lambda j: prop in j.pms_property_ids
            or j.code == f"{prefix}{context['hotel_code']}"
        )

    @api.model
    def _alda_bank_bill_term(self, bill, paid_on):
        """Days from the bill to the payment against the supplier's term."""
        bill_date = bill.invoice_date or bill.date
        supplier_term = bill.commercial_partner_id.with_company(
            bill.company_id
        ).property_supplier_payment_term_id
        term = supplier_term or bill.invoice_payment_term_id
        info = {
            "bill_date": bill_date,
            "days_since_bill": (paid_on - bill_date).days,
            "payment_term": term.name or None,
            "term_from": "supplier" if supplier_term else ("bill" if term else None),
            "agreed_days": None,
            "due_date": None,
            "late": False,
        }
        if term:
            due = max(
                (line._get_due_date(bill_date) for line in term.line_ids),
                default=bill_date,
            )
            info.update(
                agreed_days=(due - bill_date).days, due_date=due, late=paid_on > due
            )
        return info

    @api.model
    def _alda_bank_bill_info(self, bill):
        return {
            "move_id": bill.id,
            "move": bill.name,
            "supplier": bill.commercial_partner_id.name,
            "reference": truncate(bill.ref, 30),
            "bill_date": bill.invoice_date or bill.date,
            "due_date": bill.invoice_date_due,
            "amount": bill.amount_residual,
        }

    @api.model
    def _alda_bank_charge_bills(self, st_line, context, journals):
        """Open bills of the journals whose amount due is the charge, exactly."""
        currency = context["company"].currency_id
        amount = -st_line.amount
        bills = self.env["account.move"].search(
            [
                ("journal_id", "in", journals.ids),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial")),
                ("currency_id", "=", currency.id),
                ("amount_residual", ">=", amount - 0.005),
                ("amount_residual", "<=", amount + 0.005),
            ],
            order="invoice_date, id",
        )
        prop = context["property"]
        bills = bills.filtered(
            lambda b: _cents(b.amount_residual) == _cents(amount)
            and (b.invoice_date or b.date) <= st_line.date
            and (not b.pms_property_id or b.pms_property_id == prop)
        )
        partner = st_line.partner_id.commercial_partner_id
        if partner:
            bills = bills.filtered(lambda b: b.commercial_partner_id == partner)
        if len(bills) > 1:
            # Several bills for the same amount: the supplier's reference in
            # the bank concept picks one; otherwise the user decides.
            concept = _alnum(st_line.payment_ref)
            by_reference = bills.filtered(
                lambda b: len(_alnum(b.ref)) >= MIN_REFERENCE_CHARS
                and _alnum(b.ref) in concept
            )
            if len(by_reference) == 1:
                return by_reference, bills
        return bills, bills

    @api.model
    def _alda_bank_match_charge(self, st_line, context, row):
        """Fill a charge row; return the payable items to reconcile, if any."""
        journals = context.get("purchase")
        if not journals:
            row["reason"] = _(
                "The hotel has no purchase journal starting with %s: charges are "
                "not matched."
            ) % self._alda_bank_param(PARAM_PURCHASE_PREFIX)
            return None
        chosen, bills = self._alda_bank_charge_bills(st_line, context, journals)
        row["candidates"] = [
            self._alda_bank_bill_info(b) for b in bills[:MAX_BILL_CANDIDATES]
        ]
        if not bills:
            row["reason"] = _(
                "No open vendor bill of %s for this exact amount: not reconciled."
            ) % ", ".join(journals.mapped("code"))
            return None
        if len(chosen) > 1:
            row["reason"] = _(
                "%s open vendor bills for this exact amount: choose one in Odoo."
            ) % len(chosen)
            return None
        payable = chosen.line_ids.filtered(
            lambda line: line.account_id.account_type == "liability_payable"
            and not line.reconciled
        )
        if _cents(-sum(payable.mapped("amount_residual"))) != _cents(-st_line.amount):
            row["reason"] = (
                _(
                    "The payable items of %s do not add up to its amount due: "
                    "reconcile it in Odoo."
                )
                % chosen.name
            )
            return None
        row["candidates"] = [self._alda_bank_bill_info(chosen)]
        row["term"] = self._alda_bank_bill_term(chosen, st_line.date)
        if row["term"]["late"]:
            row["notice"] = self._alda_bank_late_notice(
                st_line, context, chosen, row["term"]
            )
        return payable

    @api.model
    def _alda_bank_late_notice(self, st_line, context, bill, term):
        """Draft of the message for the TAZ about a bill paid out of term."""
        return {
            "hotel": context["property"].name,
            "hotel_code": context["hotel_code"],
            "bank_date": st_line.date,
            "bank_amount": st_line.amount,
            "bill": bill.name,
            "supplier": bill.commercial_partner_id.name,
            "bill_date": term["bill_date"],
            "days_since_bill": term["days_since_bill"],
            "agreed_days": term["agreed_days"],
            "due_date": term["due_date"],
            "likely_cause": _(
                "paid %(days)s days after the bill; the agreed term is %(term)s days"
            )
            % {"days": term["days_since_bill"], "term": term["agreed_days"]},
        }

    # Positive lines: TPV settlements and transfers

    @api.model
    def _alda_bank_match_income(self, st_line, context, row, include_writeoffs):
        """Fill an income row; return the items to reconcile, if any."""
        match = self._alda_bank_match_one(st_line, context)
        row["kind"] = match["kind"]
        lines = self.env["account.move.line"]
        if len(match["exact_matches"]) == 1:
            row["candidates"] = match["exact_matches"]
            return lines.browse(match["exact_matches"][0]["move_line_id"])
        if match["exact_matches"]:
            row["candidates"] = match["exact_matches"]
            row["reason"] = _(
                "Several open entries for this exact amount: choose one with "
                "alda_bank_reconcile."
            )
        elif match["combinations"]:
            row["candidates"] = match["combinations"][0]
            row["reason"] = _(
                "Only a set of collections adds up: review it with "
                "alda_bank_reconcile."
            )
        elif match.get("grouping_pending"):
            row["reason"] = match["notes"]
        elif match["cents_writeoff"]:
            threshold = float(self._alda_bank_param(PARAM_CENTS))
            close = [
                c
                for c in match["nearby"]
                if c["date"] == match["settled_date"]
                and abs(c["difference"]) <= threshold + 1e-9
            ]
            row["candidates"] = close or match["nearby"][:MAX_BILL_CANDIDATES]
            writeoff = match["cents_writeoff"]
            if not include_writeoffs:
                row["reason"] = (
                    _(
                        "Differs by %s from the grouped entry: include write-offs or "
                        "use alda_bank_reconcile."
                    )
                    % match["difference"]
                )
            elif len(close) != 1 or not writeoff["analytic_account_id"]:
                row["reason"] = _(
                    "Differs by a few cents but there is no single grouped entry "
                    "of the settled day, or the hotel has no analytic account."
                )
            else:
                row["writeoff"] = writeoff
                return lines.browse(close[0]["move_line_id"])
        elif match["notice"]:
            row["notice"] = match["notice"]
            row["reason"] = _(
                "Nothing in Odoo adds up: send the notice with alda_bank_notify_taz."
            )
        else:
            row["reason"] = _("No open entry for this amount.")
        return None

    # The numbered table

    @api.model
    def _alda_bank_all_table(self, property_id, date_from, date_to, **options):
        """Numbered table bank vs Odoo of the pending lines of the CB journals.

        Every pending line gets a number (date, id order); the ones with a
        single exact counterpart are proposed. ``exclude`` lists the numbers
        the user left out; ``include_writeoffs`` adds the cents rule.
        """
        period = self._ai_check_period(date_from, date_to, MAX_ALL_DAYS)
        context = self._alda_bank_context(self._alda_bank_property(property_id))
        context["purchase"] = self._alda_bank_purchase_journals(context)
        st_lines = self.env["account.bank.statement.line"].search(
            [
                ("journal_id", "in", context["bank"].ids),
                ("is_reconciled", "=", False),
                ("state", "=", "posted"),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ],
            order="date, id",
        )
        if len(st_lines) > MAX_ALL_LINES:
            raise UserError(
                _(
                    "%(count)s pending lines in the period; at most %(max)s in one "
                    "call. Narrow the period."
                )
                % {"count": len(st_lines), "max": MAX_ALL_LINES}
            )
        include_writeoffs = options.get("include_writeoffs")
        exclude = set(options.get("exclude") or [])
        rows, items = [], {}
        for number, st_line in enumerate(st_lines, 1):
            row = {
                "number": number,
                "statement_line_id": st_line.id,
                "date": st_line.date,
                "amount": st_line.amount,
                "concept": truncate(st_line.payment_ref, CONCEPT_CHARS),
                "kind": "charge"
                if st_line.amount < 0
                else self._alda_bank_classify(st_line)["kind"],
                "action": "skip",
                "odoo": [],
                "candidates": [],
                "reason": "",
                "writeoff": None,
                "term": None,
                "notice": None,
            }
            # Only a line not matched in part can be reconciled here.
            if st_line._seek_for_lines()[2]:
                row["reason"] = _("Matched in part already: finish it in Odoo.")
                lines = None
            elif st_line.amount < 0:
                lines = self._alda_bank_match_charge(st_line, context, row)
            else:
                lines = self._alda_bank_match_income(
                    st_line, context, row, include_writeoffs
                )
            if lines:
                row["action"] = "reconcile"
                row["odoo"] = [self._alda_bank_candidate(line) for line in lines]
                items[number] = lines
            rows.append(row)
        self._alda_bank_all_conflicts(rows, items)
        applied = 0
        for row in rows:
            if row["action"] != "reconcile":
                continue
            if row["number"] in exclude:
                row["action"] = "excluded"
            elif applied >= MAX_ALL_RECONCILE:
                row["action"] = "next_call"
                row["reason"] = (
                    _("Over %s reconciliations: run it again afterwards.")
                    % MAX_ALL_RECONCILE
                )
            else:
                applied += 1
        totals = {}
        for row in rows:
            totals[row["action"]] = totals.get(row["action"], 0) + 1
        return {
            "period": period,
            "context": context,
            "rows": rows,
            "items": items,
            "totals": totals,
            "unknown_numbers": sorted(exclude - {row["number"] for row in rows}),
        }

    @api.model
    def _alda_bank_all_conflicts(self, rows, items):
        """An Odoo item proposed for two bank lines is proposed for none."""
        owners = {}
        for number, lines in items.items():
            for line in lines:
                owners.setdefault(line.id, []).append(number)
        clashing = {
            n for numbers in owners.values() if len(numbers) > 1 for n in numbers
        }
        for row in rows:
            if row["number"] in clashing:
                row["action"] = "skip"
                row["candidates"], row["odoo"] = row["odoo"], []
                row["writeoff"] = None
                row["reason"] = _(
                    "The same Odoo entry matches several bank lines: reconcile them "
                    "one by one."
                )
                items.pop(row["number"], None)

    @api.model
    def _alda_bank_all_definitions(self):
        return [
            _(
                "Table: every pending line of the hotel's CB journals in the period, "
                "numbered by date. action reconcile: a single Odoo counterpart with "
                "exactly the same amount; skip: nothing is done, see reason."
            ),
            _(
                "Charges (negative lines): the open vendor bill of the hotel's %s "
                "journal whose amount due is exactly the charge (same supplier when "
                "the bank line has one; the supplier's reference in the concept "
                "picks one among several). term: days since the bill against the "
                "supplier's payment term; a late payment brings a draft notice for "
                "the TAZ."
            )
            % self._alda_bank_param(PARAM_PURCHASE_PREFIX),
            _(
                "TPV settlements and transfers: the same matching as "
                "alda_bank_match_candidates, keeping only single exact matches. "
                "Combinations and differences of cents are listed to review "
                "(cents only with include_writeoffs)."
            ),
            _(
                "Notices are drafts: nothing is sent; use alda_bank_notify_taz with "
                "the statement line and the text."
            ),
        ]

    @api.model
    def _alda_bank_all_public(self, table):
        summary = _(
            "%(lines)s pending lines: %(reconcile)s to reconcile, %(excluded)s "
            "excluded, %(skip)s left as they are, %(notices)s notices to send."
        ) % {
            "lines": len(table["rows"]),
            "reconcile": table["totals"].get("reconcile", 0),
            "excluded": table["totals"].get("excluded", 0),
            "skip": table["totals"].get("skip", 0)
            + table["totals"].get("next_call", 0),
            "notices": sum(1 for row in table["rows"] if row["notice"]),
        }
        warnings = []
        if table["unknown_numbers"]:
            warnings.append(
                _("These numbers are not in the table: %s.")
                % ", ".join(map(str, table["unknown_numbers"]))
            )
        context = table["context"]
        result = {
            "hotel_code": context["hotel_code"],
            "journals": context["bank"].mapped("code"),
            "totals": table["totals"],
            "table": table["rows"],
            "notices": [
                {
                    "number": row["number"],
                    "statement_line_id": row["statement_line_id"],
                    "notice": row["notice"],
                }
                for row in table["rows"]
                if row["notice"]
            ],
        }
        return summary, warnings, result

    # Tool 8d: preview

    @guarded_tool(
        input_schema=ALL_INPUTS,
        output_schema=ALL_OUTPUT,
        required_inputs=["property_id", "date_from", "date_to"],
    )
    def _ai_alda_bank_reconcile_all_preview(
        self, property_id, date_from, date_to, include_writeoffs=False
    ):
        table = self._alda_bank_all_table(
            property_id, date_from, date_to, include_writeoffs=include_writeoffs
        )
        summary, warnings, result = self._alda_bank_all_public(table)
        return {
            "summary": summary,
            "period": table["period"],
            "definitions": self._alda_bank_all_definitions(),
            "warnings": warnings,
            "result": result,
        }

    # Tool 8e: apply

    @guarded_tool(
        input_schema=dict(
            ALL_INPUTS,
            exclude_numbers={
                "type": "array",
                "items": {"type": "integer"},
                "maxItems": MAX_ALL_LINES,
                "description": "Numbers of the table the user leaves out.",
            },
        ),
        output_schema=ALL_OUTPUT,
        required_inputs=["property_id", "date_from", "date_to"],
        write=True,
        apply="_alda_bank_reconcile_all_apply",
    )
    def _ai_alda_bank_reconcile_all(
        self,
        property_id,
        date_from,
        date_to,
        include_writeoffs=False,
        exclude_numbers=None,
    ):
        table = self._alda_bank_all_table(
            property_id,
            date_from,
            date_to,
            include_writeoffs=include_writeoffs,
            exclude=exclude_numbers,
        )
        summary, warnings, result = self._alda_bank_all_public(table)
        plan = [
            {
                "number": row["number"],
                "statement_line_id": row["statement_line_id"],
                "amount": row["amount"],
                "line_ids": table["items"][row["number"]].ids,
                "writeoff": row["writeoff"],
            }
            for row in table["rows"]
            if row["action"] == "reconcile"
        ]
        if not plan:
            raise UserError(_("Nothing to reconcile: %s") % summary)
        return {
            "summary": summary,
            "period": table["period"],
            "definitions": self._alda_bank_all_definitions()
            + [
                _(
                    "Each line is reconciled on its own. Undo: in the bank "
                    "reconciliation, open the statement line and reset it."
                )
            ],
            "warnings": warnings,
            "result": result,
            # The token signs the numbering of the whole table and what each
            # number would do: if a line comes or goes, the numbers change.
            "binding": [
                [
                    row["number"],
                    row["statement_line_id"],
                    row["amount"],
                    row["action"],
                    [c["move_line_id"] for c in row["odoo"]],
                    (row["writeoff"] or {}).get("amount"),
                ]
                for row in table["rows"]
            ],
            "plan": plan,
        }

    def _alda_bank_reconcile_all_apply(self, plan, **arguments):
        StLine = self.env["account.bank.statement.line"]
        MoveLine = self.env["account.move.line"]
        done, failed = [], []
        for item in plan:
            st_line = StLine.browse(item["statement_line_id"])
            lines = MoveLine.browse(item["line_ids"])
            try:
                with self.env.cr.savepoint():
                    if st_line.is_reconciled or any(lines.mapped("reconciled")):
                        raise UserError(_("Reconciled meanwhile."))
                    self._alda_bank_widget_reconcile(st_line, lines, item["writeoff"])
                self.env.flush_all()
                done.append(
                    {
                        "number": item["number"],
                        "statement_line_id": st_line.id,
                        "move": st_line.move_id.name,
                    }
                )
            except (UserError, ValidationError) as error:
                self.env.invalidate_all()
                failed.append(
                    {
                        "number": item["number"],
                        "statement_line_id": st_line.id,
                        "error": str(error),
                    }
                )
        warnings = []
        if failed:
            warnings.append(
                _("%s lines could not be reconciled and were left as they were.")
                % len(failed)
            )
        return {
            "summary": _("Reconciled %(done)s lines; %(failed)s failed.")
            % {"done": len(done), "failed": len(failed)},
            "definitions": [
                _(
                    "Undo: in the bank reconciliation, open the statement line and "
                    "reset it."
                ),
            ],
            "warnings": warnings,
            "result": {"reconciled": done, "failed": failed},
        }
