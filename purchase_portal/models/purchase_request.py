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

from lxml import etree
from lxml.html import builder as html

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.addons.base.models.ir_mail_server import MailDeliveryException

_logger = logging.getLogger(__name__)


class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _inherit = ['purchase.request', 'portal.mixin']

    property_id = fields.Many2one('pms.property', string='Property')

    @api.depends('state', 'review_ids')
    def _compute_access_url(self):
        super(PurchaseRequest, self)._compute_access_url()
        for purchase_request in self:
            if purchase_request.state in ["to_approve", "draft"] and not purchase_request.review_ids.filtered(lambda r: r.status == 'approved'):
                purchase_request.access_url = '/my/new_purchase_request/%s' % (purchase_request.id)
            else:
                purchase_request.access_url = '/my/purchase_requests/%s' % (purchase_request.id)

    def request_validation(self):
        res = super(PurchaseRequest, self).request_validation()
        if res.reviewer_ids:
            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            text = _("<span>A new <a href='{link}'>review {review}</a> has been asigned to you.</span>").format(
                review=self.display_name, link='%s/web#id=%s&amp;model=purchase.request&amp;view_type=form' % (base_url, self.id)
            )
            message = html.DIV(
                html.P(_('Hello,')),
                html.P(etree.fromstring(text))
            )
            body = etree.tostring(message)
            mail_factura = self.env['mail.mail'].sudo().with_context(wo_bounce_return_path=True).create({
                'subject': _('A new review has been asigned to you'),
                'body_html': body,
                'recipient_ids': res.reviewer_ids.mapped('partner_id'),
                'author_id': self.env.user.partner_id.id,
            })
            try:
                mail_factura.send(raise_exception=True)
                self.message_post(
                    body=(_("Mail sent for requested review on %s by %s") % (fields.Datetime.now(), self.env.user.display_name))
                )
            except MailDeliveryException as error:
                self.message_post(
                    body=(_("Error when sending mail for requested review: %s") % (error.args[0]))
                )
        return res


class PurchaseRequestLine(models.Model):
    _inherit = 'purchase.request.line'

    property_id = fields.Many2one('pms.property', related="request_id.property_id", string='Property', store=True)
    suggested_supplier_id = fields.Many2one('res.partner', string='Suggested Supplier')

    @api.model
    def create(self, values):
        ctx = self.env.context.copy()
        portal = ctx.get('portal', False)
        if portal:
            request_id = values.get('request_id', False)
            product_id = values.get('product_id', False)
            product_qty = values.get('product_qty', False)

            request = self.env['purchase.request'].browse(request_id)
            product = self.env['product.product'].browse(product_id)
            if not product.seller_ids:
                raise UserError(_('There are no sellers for this product in the current company.'))
            min_cost_productinfo = product.seller_ids.filtered(lambda x: x.partner_id.id in request.property_id.seller_ids.ids).sorted(key=lambda r: r.price)[0]
            if not min_cost_productinfo:
                raise UserError(_('There are no sellers allowed for this request.'))
            values['suggested_supplier_id'] = min_cost_productinfo.partner_id.id
            # min_qty = product.seller_ids.filtered(lambda x: x.name.id == request.property_id.seller_id.id).min_qty
            min_qty = min_cost_productinfo.min_qty

            if product_qty < min_qty:
                raise UserError(_('The minimum quantity for this product is %s') % min_qty)
            if request.review_ids:
                request.message_post(body=_('New line added by {user}: <strong> {product} ({quantity})</strong>'.format(user=self.env.user.name, product=product.name, quantity=product_qty)))
        return super().create(values)

    def write(self, vals):
        ctx = self.env.context.copy()
        portal = ctx.get('portal', False)
        product_qty = vals.get('product_qty', False)
        no_msg = ctx.get('no_msg', False)
        if portal and product_qty:
            min_cost_productinfo = self.product_id.seller_ids.filtered(lambda x: x.partner_id.id in self.request_id.property_id.seller_ids.ids).sorted(key=lambda r: r.price)[0]
            vals['suggested_supplier_id'] = min_cost_productinfo.partner_id.id
            # min_qty = self.product_id.seller_ids.filtered(lambda x: x.name.id == self.request_id.property_id.seller_id.id).min_qty
            min_qty = min_cost_productinfo.min_qty
            if product_qty < min_qty:
                raise UserError(_('The minimum quantity for this product is %s') % min_qty)
            if self.request_id.review_ids and not no_msg:
                self.request_id.message_post(body=_('Line edited by {user}: <strong>{product} ({old_quantity} -> {quantity})</strong>').format(user=self.env.user.name, product=self.product_id.name, old_quantity=self.product_qty, quantity=product_qty))
        return super().write(vals)

    def unlink(self):
        if self.request_id.review_ids:
            self.request_id.message_post(body=_('Line deleted by {user}: <strong> {product}</strong>').format(user=self.env.user.name, product=self.product_id.name))
        return super().unlink()

    def _autocreate_purchase_orders_from_lines(self):
        lines = self.env['purchase.request.line'].search([
            ('request_state', '=', 'approved'),
            ('purchase_state', '=', False),
        ])

        if lines:
            for hotel in lines.mapped('property_id'):
                ctx = self.env.context.copy()
                ctx['active_model'] = 'purchase.request.line'
                ctx['active_ids'] = lines.filtered(lambda r: r.property_id == hotel).ids
                wiz = self.env['purchase.request.line.make.purchase.order'].with_context(ctx).create({
                    'supplier_id': hotel.seller_ids[0].id,
                    'multiple_suppliers': True if len(hotel.seller_ids) > 1 else False,
                    'property_id': hotel.id,
                    'sync_data_planned': True,
                })
                try:
                    res = wiz.make_purchase_order()
                    orders = res['domain'][0][2]
                    orno_duplicates = []
                    [orno_duplicates.append(item) for item in orders if item not in orno_duplicates]
                    order_ids = self.env['purchase.order'].browse(orno_duplicates)
                    for order in order_ids:
                        order.button_confirm()

                        ir_model_data = self.env['ir.model.data']
                        template_id = ir_model_data.get_object_reference('purchase', 'email_template_edi_purchase_done')[1]
                        mail_wiz = self.env['mail.compose.message'].create({
                            'res_id': order.id,
                            'template_id': template_id or False,
                            'model': 'purchase.order',
                            'composition_mode': 'comment'}
                        )
                        mail_wiz.onchange_template_id_wrapper()
                        mail_wiz.action_send_mail()
                except UserError as e:
                    _logger.warning(e)
                    continue
