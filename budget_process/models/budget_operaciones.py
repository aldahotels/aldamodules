# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetOperaciones(models.Model):
    _name = "budget.operaciones"
    _description = "Operations budget"
    _inherit = "budget.base"
    department = fields.Selection(
        [("operaciones", "Operaciones")],
        default="operaciones",
        readonly=True,
    )
