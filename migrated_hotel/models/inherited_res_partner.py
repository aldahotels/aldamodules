# Copyright 2019  Pablo Q. Barriuso
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class ResPartner(models.Model):

    _inherit = 'res.partner'

    remote_id = fields.Integer(
        copy=False,
        readonly=True,
        help="ID of the target record in the previous version"
    )

    def check_vat(self):
        """
        Inherit constrain to allow migration of partner os external system
        """
        for partner in self:
            if partner.remote_id:
                continue
            else:
                super(ResPartner, partner).check_vat()
