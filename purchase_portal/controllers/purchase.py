from odoo import http, _
from odoo.http import request
import importlib

purchase = importlib.import_module('odoo.addons.purchase')


class PurchasePortal(purchase.controllers.portal.CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)

        user = request.env['res.users'].sudo().browse(request.uid)

        PurchaseOrder = request.env['purchase.order']
        if 'rfq_count' in counters:
            values['rfq_count'] = PurchaseOrder.search_count([
                ('state', 'in', ['sent']),
                ('property_id', 'in', user.pms_property_ids.ids)
            ]) if PurchaseOrder.check_access_rights('read', raise_exception=False) else 0
        if 'purchase_count' in counters:
            values['purchase_count'] = PurchaseOrder.search_count([
                ('state', 'in', ['purchase', 'done', 'cancel']),
                ('property_id', 'in', user.pms_property_ids.ids)
            ]) if PurchaseOrder.check_access_rights('read', raise_exception=False) else 0
        return values

    @http.route(['/my/purchase', '/my/purchase/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_purchase_orders(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        searchbar_filters = {
            '00-all': {'label': _('All'), 'domain': [('state', 'in', ['purchase', 'done', 'cancel'])]},
            '01-purchase': {'label': _('Purchase Order'), 'domain': [('state', '=', 'purchase')]},
            '02-delivery': {'label': _('Wating for Delivery'), 'domain': [('wating_delivery', '=', True)]},
            '03-cancel': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancel')]},
            '04-done': {'label': _('Locked'), 'domain': [('state', '=', 'done')]},
        }

        user = request.env['res.users'].sudo().browse(request.uid)
        domain = [('property_id', 'in', user.pms_property_ids.ids)]

        count = len(searchbar_filters)
        for property_id in user.pms_property_ids:
            key = str(count) + "-" + property_id.name
            if count < 10:
                key = "0" + key
            searchbar_filters[key] = {
                'label': property_id.name,
                'domain': [('property_id', '=', property_id.id)]
            }
            count += 1

        return self._render_portal(
            "purchase.portal_my_purchase_orders",
            page, date_begin, date_end, sortby, filterby,
            domain,
            searchbar_filters,
            '00-all',
            "/my/purchase",
            'my_purchases_history',
            'purchase',
            'orders'
        )
