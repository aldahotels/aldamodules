##############################################################################
#    License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
#    Copyright (C) 2023 Comunitea Servicios Tecnológicos S.L. All Rights Reserved
#    Vicente Ángel Gutiérrez <vicente@comunitea.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
import logging

from odoo import api, fields, models, _
from odoo.exceptions import Warning, UserError

from dateutil import relativedelta
from datetime import datetime, timedelta

class ResPartner(models.Model):
    _inherit = 'res.partner'

    show_in_pos = fields.Boolean(
        string="Show in pos",
        compute="_compute_show_in_pos",
        search="_search_show_in_pos",
    )

    def _compute_show_in_pos(self):
        for partner in self:
            today = datetime.now()
            date_orders = partner.pms_reservation_ids.mapped('date_order')
            if partner.pms_reservation_ids and any(relativedelta.relativedelta(date, today).months < 6 for date in date_orders):
                partner.show_in_pos = True
            else:
                partner.show_in_pos = False
    
    @api.model
    def _search_show_in_pos(self, operator, value):
        date_start = datetime.now()
        reservation_ids = self.search([('pms_reservation_ids', '!=', False)])
        reservation_within_the_year = []
        for reservation_id in reservation_ids:
            if any(relativedelta.relativedelta(date, date_start).months < 6 for date in reservation_id.mapped('pms_reservation_ids').mapped('date_order')):
                reservation_within_the_year.append(reservation_id.id)            
        return [("id", "in", reservation_within_the_year)]
    
    @api.model
    def create_from_ui(self, partner):
        partner_exists = self.search([
            ('vat', '=', partner['vat'])
        ])
        if not partner_exists and partner['country_id']:
            country_code = self.env['res.country'].browse(partner['country_id']).code
            vat = country_code + partner['vat']
            partner_exists = self.search([
                ('vat', '=', vat)
            ])
        if not partner['id'] and partner_exists:
            partner['id'] = partner_exists.id
        return super(ResPartner, self).create_from_ui(partner)
