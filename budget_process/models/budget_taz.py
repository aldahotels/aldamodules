# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetTAZ(models.Model):
    _name = "budget.taz"
    _description = "TAZ budget"
    _inherit = "budget.base"
    department = fields.Selection(
        [("taz", "Presupuestos TAZ")], default="taz", readonly=True
    )
