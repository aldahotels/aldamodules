# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AgoraTaxOverride(models.Model):
    """Workplace-specific tax overrides for Agora VAT rates"""

    _name = "agora.tax.override"
    _description = "Agora Tax Override by Workplace"

    backend_id = fields.Many2one("agora.backend", required=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", required=True)
    workplace_id = fields.Integer(
        string="Agora Workplace ID",
        required=True,
        help="Numeric ID of the Agora workplace to which this override applies",
    )
    workplace_name = fields.Char()
    vat_rate = fields.Float(
        string="Agora VAT Rate",
        required=True,
        digits=(16, 6),
        help="VAT rate from Agora as fraction (e.g. 0.10 for 10%%)",
    )
    tax_id = fields.Many2one(
        "account.tax",
        string="Odoo Tax",
        required=True,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
    )

    @api.constrains("vat_rate")
    def _check_vat_rate_range(self):
        for rec in self:
            if rec.vat_rate < 0:
                raise ValidationError(_("Agora VAT Rate cannot be negative."))

    @api.constrains("company_id", "tax_id")
    def _check_company_matches_tax(self):
        for rec in self:
            if rec.tax_id and rec.company_id != rec.tax_id.company_id:
                raise ValidationError(_("Tax company must match mapping company."))

    _sql_constraints = [
        (
            "unique_backend_workplace_company_vat",
            "unique(backend_id, company_id, workplace_id, vat_rate)",
            "Only one tax override per backend, company, workplace and VAT rate is allowed.",
        )
    ]
