import re
from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.pms_ai_tool.tools import guarded_tool, truncate

PAYROLL_ACCOUNT_PREFIX = "465"
EMPLOYEE_NUMBER = re.compile(r"\b\d{7}\b")
MAX_GROUPS = 500

REASONS = {
    "amounts_differ": "same number, amounts that do not add up to 0",
    "debit_only": "only payments, no payroll entry",
    "credit_only": "only payroll entries, no payment",
    "partners_differ": "different partners",
}

FILTER_INPUTS = {
    "date_from": {
        "type": "string",
        "format": "date",
        "description": "Only lines dated on or after this day (YYYY-MM-DD). "
        "Default: everything pending.",
    },
    "company_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "maxItems": 30,
        "description": "Companies to include. Default: all the user's.",
    },
}


def _numbers(text):
    """Distinct 7-digit numbers of a text, in order of appearance."""
    return list(dict.fromkeys(EMPLOYEE_NUMBER.findall(text or "")))


class AldaAiPayrollTools(models.AbstractModel):
    _name = "alda.ai.payroll.tools"
    _inherit = "pms.ai.tools"
    _description = "Alda AI tools: payroll accounts 465"

    # Shared by the preview and the reconciliation

    @api.model
    def _alda_payroll_465_lines(self, date_from=None, company_ids=None):
        companies = self._ai_scope_company_ids()
        if company_ids:
            foreign = set(company_ids) - set(companies)
            if foreign:
                raise UserError(
                    _("You have no access to the companies %s.")
                    % ", ".join(map(str, sorted(foreign)))
                )
            companies = list(company_ids)
        domain = [
            ("account_id.code", "=like", f"{PAYROLL_ACCOUNT_PREFIX}%"),
            ("account_id.reconcile", "=", True),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("company_id", "in", companies),
        ]
        if date_from:
            domain.append(("date", ">=", date_from))
        return self.env["account.move.line"].search(
            domain, order="company_id, account_id, date, id"
        )

    @api.model
    def _alda_payroll_465_group(self, key, lines):
        company_id, account_id, number = key
        currency = lines[0].company_id.currency_id
        debit = sum(lines.mapped("debit"))
        credit = sum(lines.mapped("credit"))
        balance = sum(lines.mapped("balance"))
        months = sorted({line.date.strftime("%Y-%m") for line in lines})
        reason = None
        if not credit:
            reason = "debit_only"
        elif not debit:
            reason = "credit_only"
        elif not currency.is_zero(balance):
            reason = "amounts_differ"
        elif len(set(lines.mapped(lambda line: line.partner_id.id))) > 1:
            reason = "partners_differ"
        return {
            "company_id": company_id,
            "company": lines[0].company_id.name,
            "account": lines[0].account_id.code,
            "account_id": account_id,
            "number": number,
            "months": months,
            "mixes_months": len(months) > 1,
            "lines": len(lines),
            "line_ids": lines.ids,
            "balances": [[line.id, line.balance] for line in lines],
            "debit": currency.round(debit),
            "credit": currency.round(credit),
            "reconcilable": reason is None,
            "reason": reason,
            "moves": sorted(set(lines.mapped("move_id.name"))),
        }

    @api.model
    def _payroll_465_build_groups(self, lines):
        """Group the 465 lines of the same employee number.

        First pass: number and month. What a month cannot settle on its own
        goes to a second pass by number only, flagged when it mixes months.
        The number is the first 7-digit number of the label, else of the
        move reference; a line with several numbers is ambiguous.
        """
        no_number = lines.browse()
        ambiguous = lines.browse()
        numbered = defaultdict(lambda: lines.browse())
        for line in lines:
            numbers = _numbers(line.name) or _numbers(line.move_id.ref)
            if not numbers:
                no_number |= line
            elif len(numbers) > 1:
                ambiguous |= line
            else:
                key = (line.company_id.id, line.account_id.id, numbers[0])
                numbered[key] |= line
        reconcilable, pending = [], []
        for key in sorted(numbered):
            by_month = defaultdict(lambda: lines.browse())
            for line in numbered[key]:
                by_month[line.date.strftime("%Y-%m")] |= line
            left = lines.browse()
            for month in sorted(by_month):
                group = self._alda_payroll_465_group(key, by_month[month])
                if group["reconcilable"]:
                    reconcilable.append(group)
                else:
                    left |= by_month[month]
            if left:
                group = self._alda_payroll_465_group(key, left)
                (reconcilable if group["reconcilable"] else pending).append(group)
        return {
            "reconcilable": reconcilable,
            "pending": pending,
            "no_number": no_number,
            "ambiguous": ambiguous,
        }

    @api.model
    def _alda_payroll_465_report(self, groups, warnings):
        """Per-company summary and the lists a person reviews."""
        by_company = defaultdict(
            lambda: {
                "reconcilable_groups": 0,
                "reconcilable_lines": 0,
                "reconcilable_amount": 0.0,
                "mixed_month_groups": 0,
                "pending": dict.fromkeys(REASONS, 0),
                "no_number_lines": 0,
                "ambiguous_lines": 0,
            }
        )
        for group in groups["reconcilable"]:
            row = by_company[group["company"]]
            row["reconcilable_groups"] += 1
            row["reconcilable_lines"] += group["lines"]
            row["reconcilable_amount"] += group["debit"]
            row["mixed_month_groups"] += group["mixes_months"]
        for group in groups["pending"]:
            by_company[group["company"]]["pending"][group["reason"]] += 1
        for field, recordset in (
            ("no_number_lines", groups["no_number"]),
            ("ambiguous_lines", groups["ambiguous"]),
        ):
            for line in recordset:
                by_company[line.company_id.name][field] += 1

        def public(group):
            return {
                key: group[key]
                for key in (
                    "company",
                    "account",
                    "number",
                    "months",
                    "mixes_months",
                    "lines",
                    "debit",
                    "credit",
                    "moves",
                )
            }

        def loose(line):
            return {
                "company": line.company_id.name,
                "account": line.account_id.code,
                "move": line.move_id.name,
                "date": line.date,
                "label": truncate(line.name, 40),
                "debit": line.debit,
                "credit": line.credit,
            }

        return {
            "by_company": [
                dict(
                    row,
                    company=name,
                    reconcilable_amount=round(row["reconcilable_amount"], 2),
                )
                for name, row in sorted(by_company.items())
            ],
            "mixed_months": self._ai_limit_rows(
                [public(g) for g in groups["reconcilable"] if g["mixes_months"]],
                warnings,
            ),
            "pending": self._ai_limit_rows(
                [
                    dict(public(g), reason=REASONS[g["reason"]])
                    for g in groups["pending"]
                ],
                warnings,
            ),
            "without_number": self._ai_limit_rows(
                [loose(line) for line in groups["no_number"]], warnings
            ),
            "ambiguous": self._ai_limit_rows(
                [loose(line) for line in groups["ambiguous"]], warnings
            ),
        }

    @api.model
    def _alda_payroll_465_lock_warnings(self, groups, warnings):
        """Warn when breaking a reconciliation would be refused afterwards."""
        locked = 0
        for group in groups:
            company = self.env["res.company"].browse(group["company_id"])
            if company.reconcile_lock_scope != "all":
                continue
            lock_date = company._get_reconcile_lock_date()
            lines = self.env["account.move.line"].browse(group["line_ids"])
            if any(line.date <= lock_date for line in lines):
                locked += 1
        if locked:
            warnings.append(
                _(
                    "%s groups have lines in a locked period: once reconciled, "
                    "'Unreconcile' will be refused for them."
                )
                % locked
            )

    @api.model
    def _alda_payroll_465_definitions(self):
        return [
            _(
                "Lines: journal items of reconcilable accounts starting with 465, "
                "posted and not reconciled."
            ),
            _(
                "Number: the first 7-digit number of the label or, if it has none, "
                "of the entry reference. A label with several numbers is ambiguous "
                "and left out."
            ),
            _(
                "Reconcilable group: debit and credit lines of the same company, "
                "account and number that add up to exactly 0, with one partner or "
                "none. First by number and month; what is left, by number only "
                "(flagged as mixing months)."
            ),
        ]

    # Tool 6

    @guarded_tool(
        input_schema=FILTER_INPUTS,
        output_schema={
            "by_company": {"type": "array", "items": {"type": "object"}},
            "mixed_months": {"type": "array", "items": {"type": "object"}},
            "pending": {"type": "array", "items": {"type": "object"}},
            "without_number": {"type": "array", "items": {"type": "object"}},
            "ambiguous": {"type": "array", "items": {"type": "object"}},
        },
        log_result=False,
    )
    def _ai_alda_payroll_465_preview(self, date_from=None, company_ids=None):
        lines = self._alda_payroll_465_lines(date_from, company_ids)
        groups = self._payroll_465_build_groups(lines)
        warnings = []
        self._alda_payroll_465_lock_warnings(groups["reconcilable"], warnings)
        result = self._alda_payroll_465_report(groups, warnings)
        return {
            "summary": _(
                "%(groups)s groups can be reconciled (%(mixed)s mix months); "
                "%(pending)s do not add up, %(loose)s lines have no clear number."
            )
            % {
                "groups": len(groups["reconcilable"]),
                "mixed": sum(g["mixes_months"] for g in groups["reconcilable"]),
                "pending": len(groups["pending"]),
                "loose": len(groups["no_number"]) + len(groups["ambiguous"]),
            },
            "period": {"date_from": date_from} if date_from else {},
            "definitions": self._alda_payroll_465_definitions(),
            "warnings": warnings,
            "result": result,
        }

    # Tool 6b

    @guarded_tool(
        input_schema=dict(
            FILTER_INPUTS,
            max_groups={
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_GROUPS,
                "description": f"Groups reconciled in one call (at most {MAX_GROUPS}).",
            },
        ),
        output_schema={
            "groups": {"type": "integer"},
            "by_company": {"type": "array", "items": {"type": "object"}},
        },
        write=True,
        apply="_alda_payroll_465_reconcile_apply",
        log_result=False,
    )
    def _ai_alda_payroll_465_reconcile(
        self, date_from=None, company_ids=None, max_groups=MAX_GROUPS
    ):
        lines = self._alda_payroll_465_lines(date_from, company_ids)
        groups = self._payroll_465_build_groups(lines)
        selected = groups["reconcilable"][:max_groups]
        warnings = []
        if len(groups["reconcilable"]) > len(selected):
            warnings.append(
                _("Only %(shown)s of %(total)s groups go in this call.")
                % {"shown": len(selected), "total": len(groups["reconcilable"])}
            )
        self._alda_payroll_465_lock_warnings(selected, warnings)
        report = self._alda_payroll_465_report(
            dict(groups, reconcilable=selected, pending=[]), warnings
        )
        return {
            "summary": _(
                "Reconcile %(groups)s groups (%(lines)s lines) of the 465 accounts."
            )
            % {"groups": len(selected), "lines": sum(g["lines"] for g in selected)},
            "period": {"date_from": date_from} if date_from else {},
            "definitions": self._alda_payroll_465_definitions()
            + [
                _(
                    "Each group is reconciled on its own; it can be undone from "
                    "Odoo with 'Unreconcile'."
                )
            ],
            "warnings": warnings,
            "result": {
                "groups": len(selected),
                "by_company": report["by_company"],
                "mixed_months": report["mixed_months"],
            },
            # The token signs the exact lines and amounts of every group.
            "binding": [g["balances"] for g in selected],
            "plan": selected,
        }

    def _alda_payroll_465_reconcile_apply(
        self, plan, date_from=None, company_ids=None, max_groups=MAX_GROUPS
    ):
        move_lines = self.env["account.move.line"]
        done, failed = [], []
        for group in plan:
            lines = move_lines.browse(group["line_ids"])
            try:
                with self.env.cr.savepoint():
                    if any(lines.mapped("reconciled")):
                        raise UserError(_("Some lines were reconciled meanwhile."))
                    lines.reconcile()
                done.append(group)
            except (UserError, ValidationError) as error:
                failed.append(
                    {
                        "company": group["company"],
                        "account": group["account"],
                        "number": group["number"],
                        "error": str(error),
                    }
                )
        warnings = []
        if failed:
            warnings.append(
                _("%s groups could not be reconciled and were left as they were.")
                % len(failed)
            )
        return {
            "summary": _("Reconciled %(done)s groups; %(failed)s failed.")
            % {"done": len(done), "failed": len(failed)},
            "definitions": [
                _("Undo: 'Unreconcile' on the journal items in Odoo."),
            ],
            "warnings": warnings,
            "result": {
                "groups": len(done),
                "by_company": [
                    {
                        "company": company,
                        "groups": sum(1 for g in done if g["company"] == company),
                        "lines": sum(
                            g["lines"] for g in done if g["company"] == company
                        ),
                    }
                    for company in sorted({g["company"] for g in done})
                ],
                "failed": failed,
            },
        }
