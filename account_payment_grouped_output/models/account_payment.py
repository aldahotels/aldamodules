from odoo import _, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    grouped_payments_move_id = fields.Many2one(
        "account.move",
        string="Grouped Payments Move",
        compute="_compute_grouped_payments_move_id",
        help="Automatic grouping move that reconciled this payment together "
        "with other outstanding payments.",
    )

    def _compute_grouped_payments_move_id(self):
        for payment in self:
            payment.grouped_payments_move_id = (
                payment.move_id.line_ids._get_grouped_payments_move()
            )

    def button_open_grouped_payments_move(self):
        self.ensure_one()
        return {
            "name": _("Grouped Payments Move"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.grouped_payments_move_id.id,
        }
