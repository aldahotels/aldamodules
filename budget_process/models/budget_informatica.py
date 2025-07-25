# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetInformatica(models.Model):
    _name = "budget.informatica"
    _description = "IT budget"
    _inherit = "budget.base"
    department = fields.Selection(
        [("informatica", "Informática")],
        default="informatica",
        readonly=True,
    )
