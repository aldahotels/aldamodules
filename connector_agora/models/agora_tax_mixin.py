# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AgoraTaxMixin(models.AbstractModel):
    """Common fields, checks and cache invalidation for Agora tax mappings.

    Shared by agora.tax.mapping and agora.tax.override. Any change on them
    clears the ormcache of agora.backend._get_mapped_tax_id.
    """

    _name = "agora.tax.mixin"
    _description = "Agora Tax Mapping Mixin"

    backend_id = fields.Many2one("agora.backend", required=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", required=True)
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.clear_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.clear_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.clear_caches()
        return res
