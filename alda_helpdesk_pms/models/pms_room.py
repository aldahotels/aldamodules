from odoo import fields, models


class PmsRoom(models.Model):
    _inherit = "pms.room"

    # Inverse of pms.reservation.line.room_id. Lets ticket computes depend on
    # the room's blocking data (out-of-service lines and closure reason).
    reservation_line_ids = fields.One2many(
        comodel_name="pms.reservation.line",
        inverse_name="room_id",
        string="Reservation Lines",
    )
