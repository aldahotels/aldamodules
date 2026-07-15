from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _get_grouped_payments_move(self):
        """Return the automatic grouping move that reconciled any of these
        lines with an outstanding payments grouping entry, if any.

        Detected structurally (no dedicated flag needed) by looking for the
        counterpart reversal line created in
        ``AccountJournal._create_grouping_move_for_lines``. It supports both
        legacy and new conventions:
        - Reverse:<payment_line_id>
        - Reverse:<payment_move_name>
        """
        counterpart_lines = self.env["account.move.line"]
        expected_names = set()
        for line in self:
            counterpart_lines |= line.matched_debit_ids.debit_move_id
            counterpart_lines |= line.matched_credit_ids.credit_move_id
            expected_names.add("Reverse:%s" % line.id)
            if line.move_name:
                expected_names.add("Reverse:%s" % line.move_name)

        grouping_lines = counterpart_lines.filtered(
            lambda l: l.name in expected_names
        )
        return grouping_lines.move_id[:1]
