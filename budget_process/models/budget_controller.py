# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetController(models.Model):
    _name = "budget.controller"
    _description = "Controller budget"
    _inherit = "budget.base"
    department = fields.Selection(
        [("controller", "Controller")],
        default="controller",
        readonly=True,
    )
