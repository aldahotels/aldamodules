# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class BudgetRN(models.Model):
    _name = "budget.rn"
    _description = "Budget Room Nights"
    _inherit = "budget.base"
    _rec_name = "name"

    name = fields.Char(
        compute="_compute_name",
        store=True,
        readonly=True,
    )
