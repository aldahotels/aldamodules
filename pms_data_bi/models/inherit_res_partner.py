# Copyright 2022 Jose Luis Algara
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResPartner(models.Model):

    _inherit = "res.partner"

    # Fields declaration
    data_bi_ref = fields.Char(string="Reference to use in DataBi (MOP)", required=False)
