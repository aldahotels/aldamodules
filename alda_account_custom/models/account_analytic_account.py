from odoo import models


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"
    _rec_name_search = ["name", "code"]