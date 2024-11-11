# Copyright 2019  Pablo Q. Barriuso
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class MigratePartner(models.Model):
    _name = 'migrated.partner'

    date_time = fields.Datetime()
    migrated_hotel_id = fields.Many2one('migrated.hotel')
    remote_id = fields.Integer(
        copy=False, readonly=True,
        help="ID of the remote record in the previous version")
    partner_id = fields.Many2one(
        string="V14 Partner",
        comodel_name="res.partner"
    )
