# Copyright 2019  Pablo Q. Barriuso
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class PmsCheckinPartner(models.Model):

    _inherit = 'pms.checkin.partner'

    remote_id = fields.Integer(
        copy=False,
        readonly=True,
        help="ID of the target record in the previous version"
    )
