import re
from datetime import date, datetime, timedelta

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from odoo.addons.pms_ai_tool.tools import guarded_tool, truncate

from .alda_ai_bank import PARAM_CENTS, _cents
from .alda_ai_bank_all import ALL_OUTPUT, MAX_ALL_DAYS, MAX_ALL_LINES
from .alda_bank_merchant import JOURNAL_TYPES

PARAM_SABADELL_PREFIX = "alda_ai_tool.sabadell_journal_prefix"
PARAM_SABADELL_POS = "alda_ai_tool.sabadell_pos_concept"
PARAM_SABADELL_CASH = "alda_ai_tool.sabadell_cash_concept"
PARAM_SABADELL_CENTS = "alda_ai_tool.sabadell_cents_threshold"
PARAM_SABADELL_JOURNALS = {
    "ca": "alda_ai_tool.sabadell_transfer_prefix",
    "ta": "alda_ai_tool.sabadell_terminal_prefix",
    "va": "alda_ai_tool.sabadell_provider_prefix",
    "wa": "alda_ai_tool.sabadell_kiosk_prefix",
}
SABADELL_DEFAULTS = {
    # Concept of a card settlement; the first group is the merchant number.
    PARAM_SABADELL_POS: r"POS\s+SETTLEMENT\D*(\d+)",
    PARAM_SABADELL_CASH: r"CASH\s+DEPOSIT",
    "alda_ai_tool.sabadell_transfer_prefix": "CA",
    "alda_ai_tool.sabadell_terminal_prefix": "TA",
    "alda_ai_tool.sabadell_provider_prefix": "VA",
    "alda_ai_tool.sabadell_kiosk_prefix": "WA",
}
# A Monday or the day after a holiday pays several days, one line each.
SETTLEMENT_DAYS = 5
HISTORY_LINES = 50
NOTES_CHARS = 200
NOTE_DATE = r"\b{}\b\W{{0,5}}(\d{{4}}-\d{{2}}-\d{{2}}|\d{{2}}/\d{{2}}/\d{{4}})"
MERCHANT_TYPES = [key for key, _label in JOURNAL_TYPES]

SABADELL_INPUTS = {
    "property_id": {"type": "integer", "description": "Hotel (pms.property)."},
    "date_from": {"type": "string", "format": "date"},
    "date_to": {
        "type": "string",
        "format": "date",
        "description": f"Included, at most {MAX_ALL_DAYS} days after date_from.",
    },
}
SABADELL_OUTPUT = dict(
    ALL_OUTPUT,
    merchants={"type": "array", "items": {"type": "object"}},
)


def _merchant_key(text):
    """Digits of a merchant number without leading zeros."""
    digits = re.sub(r"\D", "", text or "")
    return digits.lstrip("0") or digits


def _parse_day(text):
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


class AldaAiBankSabadellTools(models.AbstractModel):
    """Sabadell tools, on top of the CaixaBank ones (charges, numbered table)."""

    _name = "alda.ai.bank.sabadell.tools"
    _inherit = "alda.ai.bank.tools"
    _description = "Alda AI tools: Sabadell bank reconciliation"

    # Configuration and context

    @api.model
    def _alda_sabadell_param(self, key):
        return (
            self.env["ir.config_parameter"].sudo().get_param(key)
            or SABADELL_DEFAULTS[key]
        )

    @api.model
    def _alda_sabadell_regex(self, key, groups=0):
        pattern = self._alda_sabadell_param(key)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = None
        if regex is None or regex.groups < groups:
            raise UserError(
                _("The system parameter %(key)s is not a valid pattern: %(value)s")
                % {"key": key, "value": pattern}
            )
        return regex

    @api.model
    def _alda_sabadell_context(self, prop):
        """Sabadell bank journal and the CA, TA, VA and WA journals of a hotel."""
        prefix = self.env["ir.config_parameter"].sudo().get_param(PARAM_SABADELL_PREFIX)
        if not prefix:
            raise UserError(
                _(
                    "The Sabadell journal of the hotels is not configured: an "
                    "administrator must set the system parameter %s to the code "
                    "prefix of the hotels' Sabadell bank journals (the journal where "
                    "the Sabadell statements are imported). Nothing was read."
                )
                % PARAM_SABADELL_PREFIX
            )
        journals = self.env["account.journal"].search(
            [("type", "in", ("bank", "cash")), ("pms_property_ids", "in", prop.id)]
        )

        def coded(start):
            return journals.filtered(lambda j: (j.code or "").startswith(start))

        bank = coded(prefix).filtered(lambda j: j.type == "bank")
        if not bank:
            raise UserError(
                _("The property %(prop)s has no bank journal starting with %(prefix)s.")
                % {"prop": prop.name, "prefix": prefix}
            )
        company = bank[0].company_id
        types = {
            key: coded(self._alda_sabadell_param(param))
            for key, param in PARAM_SABADELL_JOURNALS.items()
        }
        accounts = (
            company.account_journal_payment_debit_account_id
            | company.account_journal_payment_credit_account_id
        )
        for journal in bank.union(*types.values()):
            accounts |= (
                journal.inbound_payment_method_line_ids.payment_account_id
                | journal.outbound_payment_method_line_ids.payment_account_id
            )
        context = {
            "property": prop,
            "company": company,
            "bank": bank,
            "types": types,
            "hotel_code": re.sub(r"^\D+", "", bank[0].code),
            "accounts": accounts,
            "merchants": {},
        }
        context["purchase"] = self._alda_bank_purchase_journals(context)
        return context

    @api.model
    def _alda_sabadell_parse(self, st_line):
        concept = st_line.payment_ref or ""
        pos = self._alda_sabadell_regex(PARAM_SABADELL_POS, groups=1).search(concept)
        if pos and st_line.amount:
            return {"kind": "pos", "merchant": _merchant_key(pos.group(1))}
        if self._alda_sabadell_regex(PARAM_SABADELL_CASH).search(concept):
            return {"kind": "cash", "merchant": None}
        return {
            "kind": "transfer" if st_line.amount > 0 else "charge",
            "merchant": None,
        }

    @api.model
    def _alda_sabadell_note_dates(self, st_line):
        """made_on and posting_date written in the notes of the statement line."""
        text = html2plaintext(st_line.narration) if st_line.narration else ""
        dates = {}
        for key in ("made_on", "posting_date"):
            found = re.search(NOTE_DATE.format(key), text, re.IGNORECASE)
            dates[key] = _parse_day(found.group(1)) if found else None
        dates["notes"] = truncate(text, NOTES_CHARS) or None
        return dates

    # Merchant numbers

    @api.model
    def _alda_sabadell_provider_codes(self, prop):
        """Merchant codes of the hotel's Redsys providers (P&S, journal VA)."""
        Provider = self.env["payment.provider"].sudo()
        if "redsys_merchant_code" not in Provider._fields:
            return set()
        providers = Provider.search(
            [("code", "=", "redsys"), ("pms_property_ids", "in", prop.id)]
        )
        return {
            _merchant_key(provider.redsys_merchant_code)
            for provider in providers
            if provider.redsys_merchant_code
        }

    @api.model
    def _alda_sabadell_journal_type(self, context, journal):
        for key, journals in context["types"].items():
            if journal in journals:
                return key
        return journal.code

    @api.model
    def _alda_sabadell_history(self, context, merchant):
        """(date, journal type) of the past reconciled settlements of a number."""
        st_lines = self.env["account.bank.statement.line"].search(
            [
                ("journal_id", "in", context["bank"].ids),
                ("is_reconciled", "=", True),
                ("payment_ref", "ilike", merchant),
            ],
            order="date desc, id desc",
            limit=HISTORY_LINES,
        )
        history = []
        for st_line in st_lines:
            parsed = self._alda_sabadell_parse(st_line)
            if parsed["merchant"] != merchant:
                continue
            other = st_line._seek_for_lines()[2]
            counterparts = (
                other.matched_debit_ids.debit_move_id
                | other.matched_credit_ids.credit_move_id
            )
            for kind in {
                self._alda_sabadell_journal_type(context, journal)
                for journal in counterparts.journal_id
            }:
                history.append((st_line.date, kind))
        return history

    @api.model
    def _alda_sabadell_merchant(self, context, merchant):
        """Journal type of a merchant number: provider code, confirmed or history."""
        cache = context["merchants"]
        if merchant in cache:
            return cache[merchant]
        prop = context["property"]
        if "provider_codes" not in context:
            context["provider_codes"] = self._alda_sabadell_provider_codes(prop)
        stored = (
            self.env["alda.bank.merchant"]
            .sudo()
            .search([("property_id", "=", prop.id), ("merchant", "=", merchant)])
        )
        history = self._alda_sabadell_history(context, merchant)
        counts = {}
        for _day, kind in history:
            counts[kind] = counts.get(kind, 0) + 1
        info = {
            "merchant": merchant,
            "type": None,
            "source": "unknown",
            "to_confirm": False,
            "history": counts,
            "warning": None,
        }
        if merchant in context["provider_codes"]:
            info.update(type="va", source="payment_provider")
            if stored and stored.journal_type != "va":
                info["warning"] = _(
                    "The number %(merchant)s is the merchant code of a payment "
                    "provider of the hotel (VA) but it was stored as %(type)s: "
                    "check it before reconciling."
                ) % {"merchant": merchant, "type": stored.journal_type.upper()}
        elif stored:
            info.update(type=stored.journal_type, source="confirmed")
        elif len(counts) == 1 and next(iter(counts)) in MERCHANT_TYPES:
            info.update(type=next(iter(counts)), source="history", to_confirm=True)
        if info["type"] and not info["warning"] and info["source"] != "history":
            since = stored.write_date.date() if stored else date.min
            others = sorted(
                {kind for day, kind in history if day >= since} - {info["type"]}
            )
            if others:
                info["warning"] = _(
                    "The number %(merchant)s (%(type)s) has also been reconciled "
                    "with %(others)s: check which journal it settles."
                ) % {
                    "merchant": merchant,
                    "type": info["type"].upper(),
                    "others": ", ".join(o.upper() for o in others),
                }
        cache[merchant] = info
        return info

    # Matching of a Sabadell line

    @api.model
    def _alda_sabadell_open_lines(self, context, journals, sign, date_from, date_to):
        """Open grouped entries (not single payments) with the sign of the line."""
        lines = self.env["account.move.line"].search(
            [
                ("journal_id", "in", journals.ids),
                ("account_id", "in", context["accounts"].ids),
                ("reconciled", "=", False),
                ("parent_state", "=", "posted"),
                ("amount_residual", ">" if sign > 0 else "<", 0),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("move_id.statement_line_id", "=", False),
                ("move_id.payment_id", "=", False),
            ],
            order="date, id",
        )
        return lines

    @api.model
    def _alda_sabadell_breakdown(self, context, journals, day):
        """Collections minus refunds of the journals on a day, by payment method."""
        currency = context["company"].currency_id
        payments = self.env["account.payment"].search(
            [
                ("journal_id", "in", journals.ids),
                ("date", "=", day),
                ("state", "=", "posted"),
            ]
        )
        methods = {}
        for payment in payments:
            name = payment.payment_method_line_id.name or "-"
            sign = 1 if payment.payment_type == "inbound" else -1
            methods[name] = currency.round(
                methods.get(name, 0.0) + sign * payment.amount
            )
        return {
            "date": day,
            "by_method": methods,
            "net": currency.round(sum(methods.values())),
            "payments": len(payments),
        }

    @api.model
    def _alda_sabadell_match_pos(self, st_line, context, row, merchant):
        info = self._alda_sabadell_merchant(context, merchant)
        row["merchant"] = info
        if info["warning"]:
            row["reason"] = info["warning"]
            return None
        if not info["type"]:
            row["reason"] = _(
                "Unknown merchant number and no clear history: tell which journal "
                "it settles (TA terminal or WA kiosk) with "
                "alda_bank_sabadell_merchant. Not reconciled."
            )
            return None
        journals = context["types"][info["type"]]
        if not journals:
            row["reason"] = _("The hotel has no journal of type %s.") % (
                info["type"].upper()
            )
            return None
        sign = 1 if st_line.amount > 0 else -1
        lines = self._alda_sabadell_open_lines(
            context,
            journals,
            sign,
            st_line.date - timedelta(days=SETTLEMENT_DAYS),
            st_line.date,
        )
        exact = lines.filtered(
            lambda line: _cents(line.amount_residual) == _cents(st_line.amount)
        )
        row["candidates"] = [self._alda_bank_candidate(line) for line in exact]
        if info["to_confirm"]:
            row["reason"] = _(
                "The journal type %(type)s comes from the history of the number: "
                "confirm it with alda_bank_sabadell_merchant before reconciling."
            ) % {"type": info["type"].upper()}
            return None
        if len(exact) == 1:
            return exact
        if exact:
            row["reason"] = _(
                "Several open grouped entries for this exact amount: see the "
                "chronological proposal and reconcile them by hand."
            )
            return None
        row["candidates"] = [
            self._alda_bank_candidate(line, st_line.amount) for line in lines
        ]
        closest = min(
            row["candidates"], key=lambda c: abs(c["difference"]), default=None
        )
        day = closest["date"] if closest else st_line.date - timedelta(days=1)
        row["breakdown"] = self._alda_sabadell_breakdown(context, journals, day)
        threshold = float(
            self.env["ir.config_parameter"].sudo().get_param(PARAM_SABADELL_CENTS)
            or self._alda_bank_param(PARAM_CENTS)
        )
        if closest and abs(closest["difference"]) <= threshold + 1e-9:
            row["reason"] = _(
                "Differs by %(diff)s from the entry of %(day)s, within the "
                "tolerance of %(cents)s: to confirm; not reconciled by this tool."
            ) % {"diff": closest["difference"], "day": day, "cents": threshold}
        else:
            row["reason"] = _(
                "No grouped entry of the journal %(journals)s for this exact "
                "amount: see the collections of the day by payment method."
            ) % {"journals": ", ".join(journals.mapped("code"))}
        return None

    @api.model
    def _alda_sabadell_match_transfer(self, st_line, context, row):
        journals = context["types"]["ca"]
        if not journals:
            row["reason"] = _("The hotel has no journal of type %s.") % "CA"
            return None
        lines = self._alda_bank_open_lines(
            context, journals, st_line.date, st_line.date + timedelta(days=1)
        )
        exact = lines.filtered(
            lambda line: _cents(line.amount_residual) == _cents(st_line.amount)
        )
        row["candidates"] = [self._alda_bank_candidate(line) for line in exact]
        if len(exact) == 1:
            return exact
        row["reason"] = (
            _("Several open entries for this exact amount: choose one in Odoo.")
            if exact
            else _("No open collection of %s for this exact amount.")
            % ", ".join(journals.mapped("code"))
        )
        return None

    @api.model
    def _alda_sabadell_match(self, st_line, context, row):
        parsed = self._alda_sabadell_parse(st_line)
        row["kind"] = parsed["kind"]
        row["extras"] = self._alda_sabadell_note_dates(st_line)
        row["merchant"] = None
        row["breakdown"] = None
        if parsed["kind"] == "pos":
            return self._alda_sabadell_match_pos(
                st_line, context, row, parsed["merchant"]
            )
        if parsed["kind"] == "cash":
            row["reason"] = _(
                "Cash deposit: never reconciled automatically (its matching entry "
                "is not defined yet); reconcile it by hand."
            )
            return None
        if parsed["kind"] == "charge":
            return self._alda_bank_match_charge(st_line, context, row)
        return self._alda_sabadell_match_transfer(st_line, context, row)

    @api.model
    def _alda_sabadell_order(self, context, rows):
        """Pair the unmatched settlements of each number with the open grouped
        entries in chronological order: a proposal to confirm, never applied."""
        groups = {}
        for row in rows:
            if row["kind"] != "pos" or row["action"] != "skip" or not row["merchant"]:
                continue
            info = row["merchant"]
            if not info["type"] or info["warning"]:
                continue
            sign = 1 if row["amount"] > 0 else -1
            groups.setdefault((info["merchant"], info["type"], sign), []).append(row)
        used = {line_id for row in rows for line_id in row.get("odoo_ids", [])}
        for (_merchant, kind, sign), group in groups.items():
            group.sort(
                key=lambda r: (
                    r["extras"]["made_on"] or r["date"],
                    r["extras"]["posting_date"] or r["date"],
                    r["number"],
                )
            )
            first = min(r["date"] for r in group)
            last = max(r["date"] for r in group)
            lines = self._alda_sabadell_open_lines(
                context,
                context["types"][kind],
                sign,
                first - timedelta(days=SETTLEMENT_DAYS),
                last,
            ).filtered(lambda line: line.id not in used)
            for row, line in zip(group, lines):
                row["order_proposal"] = dict(
                    self._alda_bank_candidate(line, row["amount"]), to_confirm=True
                )

    @api.model
    def _alda_sabadell_table(self, property_id, date_from, date_to, exclude=None):
        period = self._ai_check_period(date_from, date_to, MAX_ALL_DAYS)
        context = self._alda_sabadell_context(self._alda_bank_property(property_id))
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

        def match(st_line, row):
            return self._alda_sabadell_match(st_line, context, row)

        table = self._alda_bank_numbered_table(
            st_lines, match, exclude, concept=lambda st_line: st_line.payment_ref
        )
        for row in table["rows"]:
            row.setdefault("extras", None)
            row.setdefault("merchant", None)
            row.setdefault("breakdown", None)
            row["odoo_ids"] = [c["move_line_id"] for c in row["odoo"]]
            row["order_proposal"] = None
        self._alda_sabadell_order(context, table["rows"])
        for row in table["rows"]:
            del row["odoo_ids"]
        return dict(table, period=period, context=context)

    @api.model
    def _alda_sabadell_definitions(self):
        return [
            _(
                "Table: every pending line of the hotel's Sabadell journals in the "
                "period, numbered by date, with the full concept and the extras of "
                "its notes (made_on, posting_date). action reconcile: a single Odoo "
                "counterpart with exactly the same amount; skip: nothing is done, "
                "see reason."
            ),
            _(
                "pos: card settlement; the merchant number is VA when it is the "
                "merchant code of a payment provider of the hotel, otherwise the "
                "type confirmed with alda_bank_sabadell_merchant (TA or WA). A type "
                "read from the history of the number is only a proposal to confirm. "
                "Settlements, positive or negative, match the open grouped entry of "
                "that journal with the same amount in the %s days before."
            )
            % SETTLEMENT_DAYS,
            _(
                "order_proposal: unmatched settlements of a number paired in "
                "chronological order (made_on, posting_date) with the open grouped "
                "entries; only a proposal to confirm."
            ),
            _(
                "transfer: an open collection of the CA journal on the day or the "
                "next one with exactly the same amount. cash: never reconciled "
                "automatically. charge: the single open vendor bill of the hotel's "
                "FR journal with exactly the amount, with its payment term check."
            ),
        ]

    @api.model
    def _alda_sabadell_public(self, table):
        summary, warnings, result = self._alda_bank_all_public(table)
        merchants = list(table["context"]["merchants"].values())
        result["merchants"] = merchants
        for info in merchants:
            if info["warning"]:
                warnings.append(info["warning"])
        to_confirm = [m["merchant"] for m in merchants if m["to_confirm"]]
        unknown = [m["merchant"] for m in merchants if not m["type"]]
        if to_confirm:
            warnings.append(
                _("Merchant numbers with a type to confirm: %s.")
                % ", ".join(to_confirm)
            )
        if unknown:
            warnings.append(
                _("Merchant numbers without a known journal: %s.") % ", ".join(unknown)
            )
        return summary, warnings, result

    # Tool 9: Sabadell pending lines

    @guarded_tool(
        input_schema=SABADELL_INPUTS,
        output_schema=SABADELL_OUTPUT,
        required_inputs=["property_id", "date_from", "date_to"],
        log_result=False,
    )
    def _ai_alda_bank_sabadell_pending(self, property_id, date_from, date_to):
        table = self._alda_sabadell_table(property_id, date_from, date_to)
        summary, warnings, result = self._alda_sabadell_public(table)
        return {
            "summary": summary,
            "period": table["period"],
            "definitions": self._alda_sabadell_definitions(),
            "warnings": warnings,
            "result": result,
        }

    # Tool 9b: store the journal of a merchant number

    @guarded_tool(
        input_schema={
            "property_id": {"type": "integer", "description": "Hotel (pms.property)."},
            "merchant": {
                "type": "string",
                "maxLength": 20,
                "pattern": r"\d{1,20}",
                "description": "Merchant number, digits only.",
            },
            "journal_type": {
                "type": "string",
                "enum": MERCHANT_TYPES,
                "description": "ta: Sabadell card terminal; wa: kiosk; va: payment "
                "provider P&S.",
            },
        },
        output_schema={
            "merchant": {"type": "string"},
            "journal_type": {"type": "string"},
            "journals": {"type": "array", "items": {"type": "string"}},
            "previous_type": {"type": "string"},
            "history": {"type": "object"},
        },
        required_inputs=["property_id", "merchant", "journal_type"],
        write=True,
        apply="_alda_bank_sabadell_merchant_apply",
    )
    def _ai_alda_bank_sabadell_merchant(self, property_id, merchant, journal_type):
        context = self._alda_sabadell_context(self._alda_bank_property(property_id))
        merchant = _merchant_key(merchant)
        if not merchant:
            raise UserError(_("The merchant number has no digits."))
        info = self._alda_sabadell_merchant(context, merchant)
        if info["source"] == "payment_provider" and journal_type != "va":
            raise UserError(
                _(
                    "%s is the merchant code of a payment provider of the hotel: it "
                    "settles the P&S journal (VA)."
                )
                % merchant
            )
        journals = context["types"][journal_type]
        if not journals:
            raise UserError(
                _("The hotel has no journal of type %s.") % journal_type.upper()
            )
        stored = (
            self.env["alda.bank.merchant"]
            .sudo()
            .search(
                [
                    ("property_id", "=", context["property"].id),
                    ("merchant", "=", merchant),
                ]
            )
        )
        warnings = []
        others = sorted(set(info["history"]) - {journal_type})
        if others:
            warnings.append(
                _("The number has been reconciled before with %s.")
                % ", ".join(o.upper() for o in others)
            )
        return {
            "summary": _(
                "Store that %(merchant)s settles the %(type)s journal of %(hotel)s."
            )
            % {
                "merchant": merchant,
                "type": journal_type.upper(),
                "hotel": context["property"].name,
            },
            "warnings": warnings,
            "result": {
                "merchant": merchant,
                "journal_type": journal_type,
                "journals": journals.mapped("code"),
                "previous_type": stored.journal_type or "",
                "history": info["history"],
            },
            "plan": {
                "property_id": context["property"].id,
                "merchant": merchant,
                "journal_type": journal_type,
            },
        }

    def _alda_bank_sabadell_merchant_apply(self, plan, **arguments):
        Merchant = self.env["alda.bank.merchant"].sudo()
        values = {
            "journal_type": plan["journal_type"],
            "confirmed_by_id": self.env.uid,
        }
        record = Merchant.search(
            [
                ("property_id", "=", plan["property_id"]),
                ("merchant", "=", plan["merchant"]),
            ]
        )
        if record:
            record.write(values)
        else:
            record = Merchant.create(
                dict(
                    values,
                    property_id=plan["property_id"],
                    merchant=plan["merchant"],
                )
            )
        return {
            "summary": _("%(merchant)s stored as %(type)s.")
            % {"merchant": record.merchant, "type": record.journal_type.upper()},
            "result": {"merchant_id": record.id, "journal_type": record.journal_type},
        }

    # Tool 9c: reconcile the Sabadell lines

    @guarded_tool(
        input_schema=dict(
            SABADELL_INPUTS,
            exclude_numbers={
                "type": "array",
                "items": {"type": "integer"},
                "maxItems": MAX_ALL_LINES,
                "description": "Numbers of the table the user leaves out.",
            },
        ),
        output_schema=SABADELL_OUTPUT,
        required_inputs=["property_id", "date_from", "date_to"],
        write=True,
        apply="_alda_bank_reconcile_all_apply",
        log_result=False,
    )
    def _ai_alda_bank_reconcile_sabadell(
        self, property_id, date_from, date_to, exclude_numbers=None
    ):
        table = self._alda_sabadell_table(
            property_id, date_from, date_to, exclude=exclude_numbers
        )
        summary, warnings, result = self._alda_sabadell_public(table)
        return self._alda_bank_table_write(
            table,
            summary,
            warnings,
            result,
            self._alda_sabadell_definitions(),
        )
