# Copyright 2021 Dario Lodeiros
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models, fields


class MigrateChannelType(models.Model):
    _name = 'migrated.channel.type'

    last_sync = fields.Datetime('Last syncronization')
    migrated_hotel_id = fields.Many2one('migrated.hotel', readonly=True)
    remote_name = fields.Char("Remote Channel")
    channel_type_id = fields.Many2one(
        string="Current Channel",
        comodel_name="pms.sale.channel",
    )
