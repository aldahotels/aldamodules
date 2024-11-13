from odoo import fields, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    pricelist_email_text = fields.Html(string="Pricelist Email Text Alda")
