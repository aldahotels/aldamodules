# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetCAPEX(models.Model):
    _name = "budget.capex"
    _description = "CAPEX budget"
    _inherit = "budget.base"
    department = fields.Selection([("capex", "CAPEX")], default="capex", readonly=True)

    record_type = fields.Selection(
        [
            ("account_budget", "Accounting Budget"),
            ("other", "Other"),
        ],
        required=True,
        default="room_nights",
        help="Each record type represents a different KPI calculated monthly from PMS",
    )
