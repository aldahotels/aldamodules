import logging
import re
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import plaintext2html

from odoo.addons.pms_ai_tool.tools import guarded_tool, truncate

PARAM_BANK_PREFIX = "alda_ai_tool.bank_journal_prefix"
PARAM_TPV_PREFIX = "alda_ai_tool.tpv_journal_prefix"
PARAM_TAZ_JOBS = "alda_ai_tool.taz_job_ids"
PARAM_CENTS = "alda_ai_tool.cents_threshold"
PARAM_EXPENSE_ACCOUNT = "alda_ai_tool.writeoff_expense_account_code"
PARAM_INCOME_ACCOUNT = "alda_ai_tool.writeoff_income_account_code"
DEFAULTS = {
    PARAM_BANK_PREFIX: "CB",
    PARAM_TPV_PREFIX: "TB",
    PARAM_CENTS: "0.05",
    PARAM_EXPENSE_ACCOUNT: "67800000000",
    PARAM_INCOME_ACCOUNT: "77800000000",
}
# "ON <merchant number> <DDMM of the settled day>"
TPV_CONCEPT = re.compile(r"^\s*ON\s+(\d+)(?:\s+(\d{2})(\d{2}))?\b")
CONCEPT_CHARS = 40
MAX_DAYS = 93
MAX_COMBINATION = 6
MAX_COMBINATION_CANDIDATES = 25
MAX_COMBINATIONS = 10

_logger = logging.getLogger(__name__)

STATEMENT_LINE_INPUT = {
    "type": "integer",
    "description": "Bank statement line (from alda_bank_pending_lines).",
}


def _cents(amount):
    return int(round(amount * 100))


def _settled_date(statement_date, day, month):
    """Day a TPV settlement is for: the DDMM of its concept, else the day before."""
    if day and month:
        year = statement_date.year - (int(month) > statement_date.month)
        try:
            return date(year, int(month), int(day))
        except ValueError:
            _logger.debug("Invalid DDMM %s%s in a TPV concept", day, month)
    return statement_date - timedelta(days=1)


class AldaAiBankTools(models.AbstractModel):
    _name = "alda.ai.bank.tools"
    _inherit = "pms.ai.tools"
    _description = "Alda AI tools: bank reconciliation"

    # Configuration and context

    @api.model
    def _alda_bank_param(self, key):
        return self.env["ir.config_parameter"].sudo().get_param(key) or DEFAULTS[key]

    @api.model
    def _alda_bank_context(self, prop):
        """Journals, hotel code and transit accounts of a property."""
        journals = self.env["account.journal"].search(
            [("type", "=", "bank"), ("pms_property_ids", "in", prop.id)]
        )
        bank_prefix = self._alda_bank_param(PARAM_BANK_PREFIX)
        tpv_prefix = self._alda_bank_param(PARAM_TPV_PREFIX)
        bank = journals.filtered(lambda j: (j.code or "").startswith(bank_prefix))
        tpv = journals.filtered(lambda j: (j.code or "").startswith(tpv_prefix))
        if not bank:
            raise UserError(
                _("The property %(prop)s has no bank journal starting with %(prefix)s.")
                % {"prop": prop.name, "prefix": bank_prefix}
            )
        company = bank[0].company_id
        accounts = (
            company.account_journal_payment_debit_account_id
            | company.account_journal_payment_credit_account_id
        )
        for journal in bank | tpv:
            accounts |= (
                journal.inbound_payment_method_line_ids.payment_account_id
                | journal.outbound_payment_method_line_ids.payment_account_id
            )
        return {
            "property": prop,
            "company": company,
            "bank": bank,
            "tpv": tpv,
            "hotel_code": re.sub(r"^\D+", "", bank[0].code),
            "accounts": accounts,
        }

    @api.model
    def _alda_bank_property(self, property_id):
        self._ai_scope_property_ids([property_id])
        return self.env["pms.property"].browse(property_id)

    @api.model
    def _alda_bank_statement_line(self, statement_line_id, pending=True):
        st_line = self.env["account.bank.statement.line"].browse(statement_line_id)
        if not st_line.exists():
            raise UserError(_("Unknown statement line %s.") % statement_line_id)
        allowed = set(self._ai_scope_property_ids())
        props = st_line.journal_id.pms_property_ids.filtered(lambda p: p.id in allowed)
        if not props:
            raise AccessError(
                _("You have no access to the property of this statement line.")
            )
        if pending and st_line.is_reconciled:
            raise UserError(
                _("The statement line %s is already reconciled.") % st_line.id
            )
        if pending and st_line._seek_for_lines()[2]:
            raise UserError(
                _(
                    "The statement line %s is already matched in part: finish it "
                    "in the bank reconciliation of Odoo."
                )
                % st_line.id
            )
        context = self._alda_bank_context(props[0])
        if st_line.journal_id not in context["bank"]:
            raise UserError(
                _("The statement line is not in a bank journal of the property.")
            )
        return st_line, context

    @api.model
    def _alda_bank_classify(self, st_line):
        match = TPV_CONCEPT.match(st_line.payment_ref or "")
        if match and st_line.amount > 0:
            settled = _settled_date(st_line.date, match.group(2), match.group(3))
            return {"kind": "tpv", "merchant": match.group(1), "settled_date": settled}
        return {
            "kind": "transfer" if st_line.amount > 0 else "outgoing",
            "merchant": None,
            "settled_date": None,
        }

    @api.model
    def _alda_bank_line_info(self, st_line):
        return dict(
            {
                "statement_line_id": st_line.id,
                "date": st_line.date,
                "amount": st_line.amount,
                "concept": truncate(st_line.payment_ref, CONCEPT_CHARS),
                "journal": st_line.journal_id.code,
            },
            **self._alda_bank_classify(st_line),
        )

    @api.model
    def _alda_bank_open_lines(self, context, journals, date_from, date_to):
        """Open journal items on the transit accounts: the candidates."""
        return self.env["account.move.line"].search(
            [
                ("journal_id", "in", journals.ids),
                ("account_id", "in", context["accounts"].ids),
                ("reconciled", "=", False),
                ("parent_state", "=", "posted"),
                ("amount_residual", ">", 0),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("move_id.statement_line_id", "=", False),
            ],
            order="date, id",
        )

    @api.model
    def _alda_bank_candidate(self, line, target=None):
        info = {
            "move_line_id": line.id,
            "move": line.move_id.name,
            "date": line.date,
            "amount": line.amount_residual,
            "reference": truncate(line.move_id.ref, 30),
        }
        if target is not None:
            info["difference"] = round(target - line.amount_residual, 2)
        return info

    @api.model
    def _alda_bank_combinations(self, lines, target):
        """Sets of 2 to 6 open items that add up to the bank amount exactly."""
        target_cents = _cents(target)
        items = sorted(
            (
                (_cents(line.amount_residual), line)
                for line in lines
                if 0 < _cents(line.amount_residual) <= target_cents
            ),
            key=lambda item: -item[0],
        )[:MAX_COMBINATION_CANDIDATES]
        found = []

        def search(start, remaining, chosen):
            if len(found) >= MAX_COMBINATIONS:
                return
            if remaining == 0:
                if len(chosen) >= 2:
                    found.append(list(chosen))
                return
            if len(chosen) == MAX_COMBINATION:
                return
            for index in range(start, len(items)):
                cents, line = items[index]
                if cents <= remaining:
                    chosen.append(line)
                    search(index + 1, remaining - cents, chosen)
                    chosen.pop()

        search(0, target_cents, [])
        return found, len(lines) > MAX_COMBINATION_CANDIDATES

    @api.model
    def _alda_bank_writeoff(self, context, difference):
        """Account and analytic for a difference of a few cents, or None."""
        currency = context["company"].currency_id
        if currency.is_zero(difference):
            return None
        threshold = float(self._alda_bank_param(PARAM_CENTS))
        if abs(difference) > threshold + 1e-9:
            return None
        # The bank paid in less than Odoo expects: expense; more: income.
        key = PARAM_EXPENSE_ACCOUNT if difference < 0 else PARAM_INCOME_ACCOUNT
        code = self._alda_bank_param(key)
        account = self.env["account.account"].search(
            [("code", "=", code), ("company_id", "=", context["company"].id)], limit=1
        )
        if not account:
            raise UserError(
                _("The company %(company)s has no account %(code)s for write-offs.")
                % {"company": context["company"].name, "code": code}
            )
        analytic = context["property"].analytic_account_id
        return {
            "account_id": account.id,
            "account": f"{account.code} {account.name}",
            "amount": round(difference, 2),
            "analytic_account_id": analytic.id or False,
            "analytic": analytic.name or "",
        }

    # Tool 7

    @guarded_tool(
        input_schema={
            "property_id": {"type": "integer", "description": "Hotel (pms.property)."},
            "date_from": {"type": "string", "format": "date"},
            "date_to": {
                "type": "string",
                "format": "date",
                "description": f"Included, at most {MAX_DAYS} days after date_from.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Lines listed (50).",
            },
        },
        output_schema={
            "hotel_code": {"type": "string"},
            "totals": {"type": "object"},
            "lines": {"type": "array", "items": {"type": "object"}},
        },
        required_inputs=["property_id", "date_from", "date_to"],
    )
    def _ai_alda_bank_pending_lines(self, property_id, date_from, date_to, limit=None):
        period = self._ai_check_period(date_from, date_to, MAX_DAYS)
        context = self._alda_bank_context(self._alda_bank_property(property_id))
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
        rows = [self._alda_bank_line_info(st_line) for st_line in st_lines]
        totals = {}
        for row in rows:
            total = totals.setdefault(row["kind"], {"lines": 0, "amount": 0.0})
            total["lines"] += 1
            total["amount"] = round(total["amount"] + row["amount"], 2)
        warnings = []
        return {
            "summary": _("%(count)s statement lines to reconcile in %(journals)s.")
            % {
                "count": len(rows),
                "journals": ", ".join(context["bank"].mapped("code")),
            },
            "period": period,
            "definitions": [
                _(
                    "Pending: statement lines of the hotel's bank journals "
                    "(prefix %s) not reconciled yet."
                )
                % self._alda_bank_param(PARAM_BANK_PREFIX),
                _(
                    "tpv: the concept starts with ON and the merchant number; the "
                    "settlement is for the day before (settled_date, read from the "
                    "DDMM of the concept when present). transfer: any other income. "
                    "outgoing: payments out, not covered by these tools."
                ),
                _("Concepts are cut to %s characters.") % CONCEPT_CHARS,
            ],
            "warnings": warnings,
            "result": {
                "hotel_code": context["hotel_code"],
                "totals": totals,
                "lines": self._ai_limit_rows(rows, warnings, limit),
            },
        }

    # Tool 8

    @api.model
    def _alda_bank_tpv_breakdown(self, context, settled):
        """Collections minus refunds of the TPV journal on the settled day."""
        currency = context["company"].currency_id
        payments = self.env["account.payment"].search(
            [
                ("journal_id", "in", context["tpv"].ids),
                ("date", "=", settled),
                ("state", "=", "posted"),
            ]
        )
        collections = sum(
            payments.filtered(lambda p: p.payment_type == "inbound").mapped("amount")
        )
        refunds = sum(
            payments.filtered(lambda p: p.payment_type == "outbound").mapped("amount")
        )
        return {
            "date": settled,
            "collections": currency.round(collections),
            "refunds": currency.round(refunds),
            "net": currency.round(collections - refunds),
            "payments": len(payments),
        }

    @api.model
    def _alda_bank_tpv_window(self, settled):
        return settled - timedelta(days=1), settled + timedelta(days=1)

    @api.model
    def _alda_bank_match_tpv(self, st_line, context, result):
        """Fill the TPV candidates; return the checks and Odoo's amount."""
        settled = result["settled_date"]
        lines = self._alda_bank_open_lines(
            context, context["tpv"], *self._alda_bank_tpv_window(settled)
        )
        # A settlement is matched with the grouped entry of a day, never with
        # the payments it groups.
        grouped = lines.filtered(lambda line: not line.move_id.payment_id)
        exact = sorted(
            (
                line
                for line in grouped
                if _cents(line.amount_residual) == _cents(st_line.amount)
            ),
            key=lambda line: (line.date != settled, line.date),
        )
        result["exact_matches"] = [
            dict(self._alda_bank_candidate(line), other_day=line.date != settled)
            for line in exact
        ]
        if exact:
            return [], None
        result["breakdown"] = self._alda_bank_tpv_breakdown(context, settled)
        threshold = float(self._alda_bank_param(PARAM_CENTS))
        if (
            result["breakdown"]["payments"]
            and not grouped.filtered(lambda line: line.date == settled)
            and abs(result["breakdown"]["net"] - st_line.amount) <= threshold + 1e-9
        ):
            result["grouping_pending"] = True
            result["notes"] = _(
                "The payments of the settled day add up to the bank amount but "
                "their grouped TPV entry does not exist yet: reconcile it once the "
                "daily grouping has run. Nothing to notify."
            )
            return [], None
        result["nearby"] = [
            self._alda_bank_candidate(line, st_line.amount) for line in grouped
        ]
        checks = [
            _("grouped TPV entry of the settled day and the days around it"),
            _("collections minus refunds of the TPV journal that day"),
        ]
        same_day = [c for c in result["nearby"] if c["date"] == settled]
        closest = same_day or result["nearby"]
        if closest:
            return checks, min(closest, key=lambda c: abs(c["difference"]))["amount"]
        if result["breakdown"]["payments"]:
            return checks, result["breakdown"]["net"]
        return checks, None

    @api.model
    def _alda_bank_transfer_window(self, st_line):
        return st_line.date, st_line.date + timedelta(days=1)

    @api.model
    def _alda_bank_match_transfer(self, st_line, context, result):
        """Fill the transfer candidates; return the checks and Odoo's amount."""
        lines = self._alda_bank_open_lines(
            context, context["bank"], *self._alda_bank_transfer_window(st_line)
        )
        result["exact_matches"] = [
            self._alda_bank_candidate(line)
            for line in lines
            if _cents(line.amount_residual) == _cents(st_line.amount)
        ]
        if result["exact_matches"]:
            return [], None
        combinations, capped = self._alda_bank_combinations(lines, st_line.amount)
        result["combinations"] = [
            [self._alda_bank_candidate(line) for line in combination]
            for combination in combinations
        ]
        if capped:
            result["combinations_capped"] = True
        if result["combinations"]:
            return [], None
        # Other collections of the window belong to other customers: shown as
        # context only, never as what Odoo has for this transfer.
        result["nearby"] = [
            self._alda_bank_candidate(line, st_line.amount) for line in lines
        ]
        checks = [
            _("collections of the bank journal on the day and the day after"),
            _("combinations of up to %s collections") % MAX_COMBINATION,
        ]
        return checks, None

    @api.model
    def _alda_bank_notice(self, st_line, context, result, checks, odoo_amount):
        """Draft of the message for the TAZ when nothing adds up."""
        if odoo_amount is None:
            cause = _("a collection seems to be missing in Roomdoo")
        elif result["difference"] > 0:
            cause = _("the bank has more than Odoo: a collection may be missing")
        else:
            cause = _("Odoo has more than the bank: a collection may be extra or late")
        return {
            "hotel": context["property"].name,
            "hotel_code": context["hotel_code"],
            "bank_date": st_line.date,
            "bank_amount": st_line.amount,
            "odoo_amount": odoo_amount,
            "difference": result["difference"],
            "checked": checks,
            "likely_cause": cause,
        }

    @api.model
    def _alda_bank_match_one(self, st_line, context):
        result = dict(
            self._alda_bank_line_info(st_line),
            hotel_code=context["hotel_code"],
            exact_matches=[],
            combinations=[],
            nearby=[],
            breakdown=None,
            difference=None,
            cents_writeoff=None,
            notice=None,
        )
        if result["kind"] == "tpv":
            checks, odoo_amount = self._alda_bank_match_tpv(st_line, context, result)
        elif result["kind"] == "transfer":
            checks, odoo_amount = self._alda_bank_match_transfer(
                st_line, context, result
            )
        else:
            result["notes"] = _("Outgoing lines are not covered by these tools.")
            return result
        if (
            result["exact_matches"]
            or result["combinations"]
            or result.get("grouping_pending")
        ):
            return result
        currency = context["company"].currency_id
        if odoo_amount is not None:
            result["difference"] = currency.round(st_line.amount - odoo_amount)
            if currency.is_zero(result["difference"]):
                return result
            # The cents rule covers whole TPV settlements only.
            if result["kind"] == "tpv":
                result["cents_writeoff"] = self._alda_bank_writeoff(
                    context, result["difference"]
                )
        if not result["cents_writeoff"]:
            result["notice"] = self._alda_bank_notice(
                st_line, context, result, checks, odoo_amount
            )
        return result

    @guarded_tool(
        input_schema={
            "statement_line_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 1,
                "maxItems": 20,
                "description": "Statement lines to match (from alda_bank_pending_lines).",
            },
        },
        output_schema={"lines": {"type": "array", "items": {"type": "object"}}},
        required_inputs=["statement_line_ids"],
    )
    def _ai_alda_bank_match_candidates(self, statement_line_ids):
        rows = []
        for statement_line_id in statement_line_ids:
            st_line, context = self._alda_bank_statement_line(statement_line_id)
            rows.append(self._alda_bank_match_one(st_line, context))
        matched = sum(1 for r in rows if r["exact_matches"] or r["combinations"])
        cents = sum(1 for r in rows if r["cents_writeoff"])
        notices = sum(1 for r in rows if r["notice"])
        return {
            "summary": _(
                "%(matched)s lines with candidates, %(cents)s with a difference of "
                "cents, %(notices)s to notify."
            )
            % {"matched": matched, "cents": cents, "notices": notices},
            "definitions": [
                _(
                    "Candidates: open journal items of the transit accounts. TPV: in "
                    "the TPV journal, dated the settled day (grouped entry) with the "
                    "same amount. Transfer: in the bank journal, dated the same day or "
                    "the next one, alone or in sets of up to %s items adding up "
                    "exactly."
                )
                % MAX_COMBINATION,
                _(
                    "cents_writeoff: a difference up to %(cents)s goes to %(expense)s "
                    "when the bank pays in less and to %(income)s when it pays in "
                    "more, with the hotel's analytic account."
                )
                % {
                    "cents": self._alda_bank_param(PARAM_CENTS),
                    "expense": self._alda_bank_param(PARAM_EXPENSE_ACCOUNT),
                    "income": self._alda_bank_param(PARAM_INCOME_ACCOUNT),
                },
                _(
                    "notice: draft of the message for the hotel's TAZ when nothing "
                    "adds up (alda_bank_notify_taz sends it)."
                ),
            ],
            "warnings": [],
            "result": {"lines": rows},
        }

    # Tool 8b

    @api.model
    def _alda_bank_activity_summary(self):
        return _("Bank reconciliation difference")

    @api.model
    def _alda_bank_taz_users(self, prop):
        param = self.env["ir.config_parameter"].sudo().get_param(PARAM_TAZ_JOBS)
        jobs = self.env["hr.job"].sudo()
        if param:
            jobs = jobs.browse([int(x) for x in re.findall(r"\d+", param)]).exists()
        else:
            jobs = jobs.search([("name", "ilike", "TAZ")])
        employees = (
            self.env["hr.employee"]
            .sudo()
            .search(
                [
                    ("job_id", "in", jobs.ids),
                    ("property_ids", "in", prop.id),
                    ("user_id", "!=", False),
                ]
            )
        )
        # Only internal, active users who can open the entry of that company.
        return employees.user_id.filtered(
            lambda user: user.active
            and not user.share
            and prop.company_id in user.company_ids
        )

    @guarded_tool(
        input_schema={
            "statement_line_id": STATEMENT_LINE_INPUT,
            "message": {
                "type": "string",
                "maxLength": 2000,
                "description": "Text of the notice: hotel, bank date and amount, "
                "what Odoo has, difference, checks done, likely cause. No names of "
                "guests or customers.",
            },
        },
        output_schema={
            "recipients": {"type": "array", "items": {"type": "object"}},
            "statement_line": {"type": "object"},
        },
        required_inputs=["statement_line_id", "message"],
        write=True,
        apply="_alda_bank_notify_taz_apply",
    )
    def _ai_alda_bank_notify_taz(self, statement_line_id, message):
        st_line, context = self._alda_bank_statement_line(statement_line_id)
        users = self._alda_bank_taz_users(context["property"])
        if not users:
            raise UserError(
                _("No TAZ with an active internal user is assigned to %s in Employees.")
                % context["property"].name
            )
        notified = (
            self.env["mail.activity"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "account.move"),
                    ("res_id", "=", st_line.move_id.id),
                    ("summary", "=", self._alda_bank_activity_summary()),
                    ("user_id", "in", users.ids),
                ]
            )
            .user_id
        )
        users -= notified
        if not users:
            raise UserError(
                _("The TAZ already have an open activity on %s about this line.")
                % st_line.move_id.name
            )
        return {
            "summary": _("Create an activity on %(move)s for %(users)s.")
            % {"move": st_line.move_id.name, "users": ", ".join(users.mapped("name"))},
            "definitions": [
                _(
                    "Recipients: the users of the employees whose job is TAZ and who "
                    "have the hotel among their properties."
                ),
            ],
            "result": {
                "statement_line": self._alda_bank_line_info(st_line),
                "recipients": [{"user_id": u.id, "name": u.name} for u in users],
                "message": message,
            },
            "plan": {"move_id": st_line.move_id.id, "user_ids": users.ids},
        }

    def _alda_bank_notify_taz_apply(self, plan, statement_line_id, message):
        move = self.env["account.move"].browse(plan["move_id"])
        activities = self.env["mail.activity"]
        for user_id in plan["user_ids"]:
            activities |= move.activity_schedule(
                "mail.mail_activity_data_todo",
                date_deadline=fields.Date.context_today(self),
                summary=self._alda_bank_activity_summary(),
                note=plaintext2html(message),
                user_id=user_id,
            )
        return {
            "summary": _("%(count)s activities created on %(move)s.")
            % {"count": len(activities), "move": move.name},
            "result": {
                "activity_ids": activities.ids,
                "move": move.name,
                "recipients": activities.mapped("user_id.name"),
            },
        }

    # Tool 8c

    @guarded_tool(
        input_schema={
            "statement_line_id": STATEMENT_LINE_INPUT,
            "move_line_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 1,
                "maxItems": MAX_COMBINATION,
                "description": "Open journal items to match (from "
                "alda_bank_match_candidates).",
            },
        },
        output_schema={
            "statement_line": {"type": "object"},
            "lines": {"type": "array", "items": {"type": "object"}},
            "writeoff": {"type": "object"},
        },
        required_inputs=["statement_line_id", "move_line_ids"],
        write=True,
        apply="_alda_bank_reconcile_apply",
    )
    def _ai_alda_bank_reconcile(self, statement_line_id, move_line_ids):
        st_line, context = self._alda_bank_statement_line(statement_line_id)
        lines = self.env["account.move.line"].browse(move_line_ids).exists()
        if len(lines) != len(set(move_line_ids)):
            raise UserError(_("Some journal items do not exist."))
        info = self._alda_bank_classify(st_line)
        if info["kind"] == "tpv":
            journals = context["tpv"]
            date_from, date_to = self._alda_bank_tpv_window(info["settled_date"])
        elif info["kind"] == "transfer":
            journals = context["bank"]
            date_from, date_to = self._alda_bank_transfer_window(st_line)
        else:
            raise UserError(_("Only incoming statement lines can be reconciled here."))
        wrong = lines.filtered(
            lambda line: line.reconciled
            or line.parent_state != "posted"
            or line.company_id != st_line.company_id
            or line.account_id not in context["accounts"]
            or line.journal_id not in journals
            or line.move_id.statement_line_id
            or line.amount_residual <= 0
            or not date_from <= line.date <= date_to
            # A TPV settlement goes against the grouped entry, not its payments.
            or (info["kind"] == "tpv" and line.move_id.payment_id)
        )
        if wrong:
            raise UserError(
                _(
                    "These journal items cannot be matched with this statement line "
                    "(already reconciled, not posted, outside the dates, or not the "
                    "open %(kind)s collections of the hotel): %(moves)s."
                )
                % {
                    "kind": info["kind"],
                    "moves": ", ".join(wrong.mapped("move_id.name")),
                }
            )
        currency = context["company"].currency_id
        total = currency.round(sum(lines.mapped("amount_residual")))
        difference = currency.round(st_line.amount - total)
        writeoff = (
            self._alda_bank_writeoff(context, difference)
            if info["kind"] == "tpv"
            else None
        )
        if not currency.is_zero(difference) and not writeoff:
            raise UserError(
                _(
                    "The bank line is %(bank)s and the items add up to %(odoo)s: a "
                    "difference of %(diff)s cannot be written off (the cents rule is "
                    "for whole TPV settlements). Notify the TAZ instead of "
                    "reconciling."
                )
                % {"bank": st_line.amount, "odoo": total, "diff": difference}
            )
        if writeoff and not writeoff["analytic_account_id"]:
            raise UserError(
                _("The property %s has no analytic account for the write-off.")
                % context["property"].name
            )
        return {
            "summary": _(
                "Reconcile the bank line of %(date)s for %(amount)s with %(count)s "
                "items%(writeoff)s."
            )
            % {
                "date": st_line.date,
                "amount": st_line.amount,
                "count": len(lines),
                "writeoff": _(" and a write-off of %(amount)s to %(account)s")
                % writeoff
                if writeoff
                else "",
            },
            "definitions": [
                _(
                    "Undo: in the bank reconciliation, open the statement line and "
                    "reset it."
                ),
            ],
            "result": {
                "statement_line": self._alda_bank_line_info(st_line),
                "lines": [self._alda_bank_candidate(line) for line in lines],
                "total": total,
                "difference": difference,
                "writeoff": writeoff or {},
            },
            "plan": {
                "statement_line_id": st_line.id,
                "line_ids": lines.ids,
                "writeoff": writeoff,
            },
        }

    def _alda_bank_reconcile_apply(self, plan, statement_line_id, move_line_ids):
        st_line = self.env["account.bank.statement.line"].browse(
            plan["statement_line_id"]
        )
        lines = self.env["account.move.line"].browse(plan["line_ids"])
        widget = (
            self.env["bank.rec.widget"]
            .with_context(default_st_line_id=st_line.id)
            .new({})
        )
        widget._action_add_new_amls(lines, allow_partial=False)
        writeoff = plan["writeoff"]
        if writeoff:
            balance_line = widget.line_ids.filtered(lambda l: l.flag == "auto_balance")
            if not balance_line:
                raise UserError(_("The reconciliation has no line for the write-off."))
            widget._action_mount_line_in_edit(balance_line.index)
            widget.form_account_id = self.env["account.account"].browse(
                writeoff["account_id"]
            )
            widget._onchange_form_account_id()
            widget.analytic_distribution = {str(writeoff["analytic_account_id"]): 100}
            widget._onchange_analytic_distribution()
        if widget.state != "valid":
            raise UserError(_("The reconciliation does not balance; nothing was done."))
        # The widget must propose exactly what the preview showed: the bank line,
        # the chosen items and, if any, the write-off; nothing to a partner.
        flags = widget.line_ids.mapped("flag")
        expected = sorted(["liquidity"] + ["new_aml"] * len(lines))
        if writeoff:
            expected = sorted(expected + ["manual"])
            manual = widget.line_ids.filtered(lambda l: l.flag == "manual")
            currency = st_line.company_id.currency_id
            if len(manual) != 1 or not currency.is_zero(
                manual.balance + writeoff["amount"]
            ):
                raise UserError(_("The write-off is not the one previewed."))
        if sorted(flags) != expected:
            extra = ", ".join(sorted(set(flags) - set(expected))) or "-"
            raise UserError(
                _(
                    "The bank reconciliation proposes other lines (%s); nothing was "
                    "done. Finish it in Odoo."
                )
                % extra
            )
        widget.button_validate()
        st_line.invalidate_recordset(["is_reconciled"])
        if not st_line.is_reconciled:
            raise UserError(_("The statement line could not be reconciled."))
        return {
            "summary": _("Statement line %(id)s reconciled (%(move)s).")
            % {"id": st_line.id, "move": st_line.move_id.name},
            "result": {
                "statement_line_id": st_line.id,
                "move": st_line.move_id.name,
                "reconciled": True,
            },
        }
