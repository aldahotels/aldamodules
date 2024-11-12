# Copyright 2019  Pablo Q. Barriuso
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class PmsCheckinPartner(models.Model):

    _inherit = 'pms.checkin.partner'


    def validate_id_number(self):
        """
        Inherit constrain to allow migration of partner os external system
        """
        for checkin in self:
            if checkin.folio_id.remote_id:
                continue
            else:
                super(PmsCheckinPartner, partner).validate_id_number()
