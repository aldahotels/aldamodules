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

from odoo import api, models


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def create(self, values):
        ctx = self.env.context.copy()
        res = super(PosSession, self.with_context(ctx).sudo()).create(values)
        if ctx.get('cash_register_id', False):
            cash_register_id = self.env['account.bank.statement'].browse(ctx['cash_register_id'])
            statement_ids = res.statement_ids.ids + cash_register_id.ids
            if cash_register_id:
                res.update({
                    'statement_ids': [(6, 0, statement_ids)],
                })
                res._compute_cash_all()
        return res
