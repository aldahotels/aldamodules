# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AgoraTaxOverride(models.Model):
    """Workplace-specific tax overrides for Agora VAT rates"""

    _name = "agora.tax.override"
    _inherit = "agora.tax.mixin"
    _description = "Agora Tax Override by Workplace"

    workplace_id = fields.Integer(
        string="Agora Workplace ID",
        required=True,
        help="Numeric ID of the Agora workplace to which this override applies",
    )
    workplace_name = fields.Char()

    _sql_constraints = [
        (
            "unique_backend_workplace_company_vat",
            "unique(backend_id, company_id, workplace_id, vat_rate)",
            "Only one tax override per backend, company, workplace and VAT rate is allowed.",
        )
    ]
