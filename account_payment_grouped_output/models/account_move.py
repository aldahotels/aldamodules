from odoo import _, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    reconciled_statement_line_id = fields.Many2one(
        "account.bank.statement.line",
        string="Reconciled Bank Transaction",
        compute="_compute_reconciled_statement_line_id",
        help="Bank transaction reconciled with (any line of) this journal "
        "entry, if any. Used to link an automatic payments grouping move "
        "with the bank statement line it was reconciled with.",
    )

    def _compute_reconciled_statement_line_id(self):
        for move in self:
            counterpart_lines = (
                move.line_ids.matched_debit_ids.debit_move_id
                | move.line_ids.matched_credit_ids.credit_move_id
            )
            move.reconciled_statement_line_id = (
                counterpart_lines.move_id.statement_line_id[:1]
            )

    def button_open_reconciled_statement_line(self):
        self.ensure_one()
        return {
            "name": _("Bank Transaction"),
            "type": "ir.actions.act_window",
            "res_model": "account.bank.statement.line",
            "view_mode": "form",
            "res_id": self.reconciled_statement_line_id.id,
        }
