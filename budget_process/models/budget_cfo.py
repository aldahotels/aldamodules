# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetCFO(models.Model):
    _name = "budget.cfo"
    _description = "CFO budget"
    _inherit = "budget.base"
    department = fields.Selection([("cfo", "CFO")], default="cfo", readonly=True)
