# Copyright 2020 Commitsun.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import io

from odoo import api, fields, models
from odoo.tools import float_compare, float_round, pycompat


class PmsWizardReconcile(models.TransientModel):

    _name = "pms.wizard.reconcile"
    _description = "Reconcile Payments"

    name = fields.Char("File name")
    file = fields.Binary("File")
    type = fields.Selection([("csv", "CSV")], default="csv", string="File type.")

    journal_ids = fields.Many2many("account.journal", string="Journals")

    filter_by_date = fields.Boolean("Filter by date")
    filter_from = fields.Date("Filter from")
    filter_to = fields.Date("Filter to")

    filter_by_property = fields.Boolean("Filter by property")
    pms_property_id = fields.Many2one("pms.property", "Property")

    filter_by_origin_agency = fields.Boolean("Filter by origin agency")
    origin_agency_id = fields.Many2one("pms.agency", "Origin agency")

    move_types = fields.Selection(
        string="Move types",
        selection=[("payment", "Payment"), ("invoice", "Invoice"), ("all", "All")],
        default="payment",
    )

    move_line_ids = fields.Many2many(
        "account.move.line",
        string="Move lines",
    )

    move_line_reconciled_ids = fields.Many2many(
        "account.move.line",
        string="Move lines reconciled",
        relation="pms_wizard_reconcile_move_line_reconciled_rel",
        column1="wizard_id",
        column2="move_line_id",
        readonly=True,
    )

    origin_statement_line_id = fields.Many2one(
        comodel_name="account.bank.statement.line",
        string="Origin statement line",
        default=lambda self: self._default_origin_statement_line_id(),
        required=True,
    )

    folio_ids = fields.Many2many(string="folios not found", comodel_name="pms.folio")

    file_total = fields.Float(
        string="Total in File",
        readonly=True,
    )

    origin_total = fields.Monetary(
        string="Total in Origin Statement",
        related="origin_statement_line_id.amount",
    )

    target_total = fields.Monetary(
        string="Target total", compute="_compute_target_total"
    )

    residual = fields.Monetary(string="Residual", compute="_compute_residual")

    csv_not_found = fields.Char(
        string="transactions not found",
        readonly=True,
    )
    count_csv_transactions = fields.Integer(
        string="Count CSV transactions",
        readonly=True,
    )
    count_payments_found = fields.Integer(
        string="Count Payments Found",
        readonly=True,
        compute="_compute_count_payments_found",
    )
    journal_id = fields.Many2one(
        string="Journal",
        related="origin_statement_line_id.journal_id",
    )
    company_id = fields.Many2one(
        string="Company",
        related="origin_statement_line_id.company_id",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        string="Company Currency",
        store=True,
        readonly=True,
    )
    incongruence_file = fields.Boolean(
        string="Incongruence File",
        default=False,
        readonly=True,
    )
    check_reconciled_found = fields.Boolean(
        string="Check Reconciled Found",
        compute="_compute_check_reconciled_found",
    )
    check_not_found_lines_csv = fields.Boolean(
        string="Check Not Found CSV lines",
        compute="_compute_check_not_found_lines_csv",
    )

    @api.depends("csv_not_found", "folio_ids")
    def _compute_check_not_found_lines_csv(self):
        if self.csv_not_found or self.folio_ids:
            self.check_not_found_lines_csv = True
        else:
            self.check_not_found_lines_csv = False

    @api.depends("move_line_reconciled_ids")
    def _compute_check_reconciled_found(self):
        for rec in self:
            if rec.move_line_reconciled_ids:
                rec.check_reconciled_found = True
            else:
                rec.check_reconciled_found = False

    @api.depends("move_line_ids")
    def _compute_count_payments_found(self):
        for rec in self:
            rec.count_payments_found = len(rec.move_line_ids)

    def _default_origin_statement_line_id(self):
        return self.env.context.get("active_id", False)

    @api.depends("move_line_ids")
    def _compute_target_total(self):
        for record in self:
            record.target_total = sum(record.move_line_ids.mapped("balance"))

    @api.depends("target_total")
    def _compute_residual(self):
        for record in self:
            record.residual = float_round(
                record.target_total - record.origin_statement_line_id.amount, 2
            )

    def search_move_line_ids(self):
        self.ensure_one()
        domain = [
            ("account_id.reconcile", "=", True),
            ("move_id.state", "=", "posted"),
        ]
        if self.move_types != "all":
            journal_types = ["sale"] if self.move_types == "invoice" else ["bank"]
            domain.append(("journal_id.type", "in", journal_types))
        if self.filter_by_date and self.filter_from and self.filter_to:
            domain.append(("date", ">=", self.filter_from))
            domain.append(("date", "<=", self.filter_to))
        if self.filter_by_property and self.property_id:
            domain.append(("pms_property_id", "=", self.property_id.id))
        if self.filter_by_origin_agency and self.origin_agency_id:
            domain.append(("origin_agency_id", "=", self.origin_agency_id.id))
        if self.file and self.journal_ids:
            domain.append(("id", "in", self._get_move_line_ids(self.file)))
            domain.append(("journal_id", "in", self.journal_ids.ids))
            move_lines = self.env["account.move.line"].search(domain)
            self.move_line_ids = move_lines.filtered(lambda l: not l.reconciled)
            self.move_line_reconciled_ids = move_lines.filtered(lambda l: l.reconciled)
        else:
            self.move_line_ids = False

    @api.model
    def _get_move_line_ids(self, file):
        lines = self.get_and_parse_csv(file)
        return lines.ids

    def _read_csv(self, file):
        if self.file:
            return base64.b64decode(file)

    @api.model
    def get_and_parse_csv(self, file):
        csv_data = base64.b64decode(self.file)
        csv_data = csv_data.decode("utf-8").encode("utf-8")
        reader = pycompat.csv_reader(
            io.BytesIO(csv_data),
            # delimiter=str(self.csv_delimiter),
            # quotechar=str(self.csv_quotechar)
        )
        lines = self.env["account.move.line"]
        self.count_csv_transactions = 0
        self.file_total = 0
        next(reader)
        for pay in reader:
            self.count_csv_transactions += 1
            self.file_total += float(pay[8])
            line = False
            line = self.env["account.move.line"].search(
                [
                    ("ref", "ilike", pay[1]),
                    ("balance", "=", float(pay[8])),
                ]
            )
            if line:
                lines += line
            else:
                mens = str(pay[1])
                folio = self.env["pms.folio"].search(
                    [("external_reference", "=", str(pay[1]))]
                )
                if folio:
                    self.folio_ids = [(4, folio.id)]
                else:
                    mens += "(not found)"
                    self.csv_not_found = (
                        mens
                        if not self.csv_not_found
                        else self.csv_not_found + ", " + mens
                    )
        if (
            float_compare(
                self.file_total,
                self.origin_statement_line_id.amount,
                precision_rounding=2,
            )
            != 0
        ):
            self.incongruence_file = True
        return lines

    def matching_button(self):
        self.ensure_one()
        domain = [
            ("account_internal_type", "in", ("receivable", "pay   able", "other")),
            ("reconciled", "=", False),
        ]
        statement_move_line = (
            self.origin_statement_line_id.move_id.line_ids.filtered_domain(domain)
        )
        statement_move_line.account_id = self.move_line_ids.account_id
        lines_to_reconcile = statement_move_line + self.move_line_ids
        lines_to_reconcile.reconcile()
        action = self.env.ref("account.action_bank_statement_tree").sudo().read()[0]
        action["views"] = [
            (self.env.ref("account.view_bank_statement_form").id, "form")
        ]
        action["res_id"] = self.origin_statement_line_id.statement_id.id
        return action
