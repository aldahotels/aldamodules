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

from datetime import datetime
from uuid import uuid4
import pytz
from lxml import etree
from lxml.html import builder as html

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'portal.mixin']

    def get_portal_url(self):
        res = super(StockPicking, self).get_portal_url()
        return '/my/stock_pickings/%s' % (self.id) + res

    def _create_backorder(self):
        res = super(StockPicking, self)._create_backorder()
        if self.env.context.get('backorder_message', False):
            text = self.env.context.get('backorder_message', False)
            lines = ""
            for line in res.move_lines:
                lines+= ("Product: <b>{}</b>, quantity: <b>{}</b><br/>".format(line.product_id.display_name, line.product_qty))
            message = _("Hi {}, <br/>".format(res.partner_id.name)) + text + lines

            res.message_post(
                body=message, subtype_id=self.env.ref("mail.mt_comment").id
            )
        return res
