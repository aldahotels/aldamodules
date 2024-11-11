# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models

from odoo.addons.component.core import Component


class AccountMove(models.Model):
    _inherit = "account.move"
    docuware_bind_ids = fields.One2many("docuware.account.move", "odoo_id")
    docuware_fixed_asset = fields.Boolean(
        "Fixed assets", related="docuware_bind_ids.fixed_asset", store=True
    )


class DocuwareAccountMove(models.Model):

    _name = "docuware.account.move"
    _inherit = "docuware.document"
    _inherits = {"account.move": "odoo_id"}
    _description = "Docuware invoice"

    odoo_id = fields.Many2one("account.move", required=True, ondelete="cascade")
    docuware_amount_total = fields.Float()
    fixed_asset = fields.Boolean("Fixed assets")
    partner_not_found = fields.Boolean()
    docuware_vat = fields.Char()


class AccountMoveAdapter(Component):
    _name = "docuware.account.move.adapter"
    _inherit = "docuware.document.adapter"
    _apply_on = "docuware.account.move"
