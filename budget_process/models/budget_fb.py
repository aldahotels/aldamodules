# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetFB(models.Model):
    _name = "budget.fb"
    _description = "F&B budget"
    _inherit = "budget.base"

    department = fields.Selection(
        [("fb", "Food & Beverage")],
        default="fb",
        readonly=True,
    )
