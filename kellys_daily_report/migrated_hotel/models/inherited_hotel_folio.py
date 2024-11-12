# Copyright 2019  Pablo Q. Barriuso
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class PmsFolio(models.Model):

    _inherit = 'pms.folio'

    remote_id = fields.Integer(
        copy=False,
        readonly=True,
        help="ID of the target record in the previous version"
    )
    incongruence_data_migration = fields.Boolean(
        string="Incongruence Data Migration",
        default=False,
        copy=False,
    )

