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

{
    "name": "Purchase portal",
    "summary": "Allow to make a purchase request from the portal",
    "version": "14.0.1.0.0",
    "author": "Comunitea Servicios Tecnológicos S.L.",
    "website": "www.comunitea.com",
    "license": "AGPL-3",
    "category": "Custom",
    "depends": [
        "pms",
        "portal",
        "purchase_request",
        "purchase_request_tier_validation",
        "auth_signup",
        "custom_login_by_token",
        "point_of_sale",
    ],
    "data": [
        'security/ir.model.access.csv',
        "security/request_carts_security.xml",
        'templates/assets.xml',
        'templates/purchase_request.xml',
        'templates/stock_picking.xml',
        "templates/request_saved_cart.xml",
        'views/pms_property.xml',
        'views/product_product.xml',
        'views/purchase_request.xml',
        'views/purchase_order.xml',
        'views/product_supplierinfo.xml',
        'views/res_users.xml',
        'views/res_partner.xml',
        "views/request_saved_cart.xml",
        'wizard/purchase_request_line_make_purchase_order.xml',
        'wizard/stock_backorder_confirmation_views.xml',
        'wizard/import_supplier_data_wizard.xml',
        'data/purchase_pos_send_template.xml',
        'data/purchase_order_rfq_template.xml',
        'data/purchase_order_remainder_template.xml',
    ],
    "assets": {
        "web.assets_frontend": [],
    },
    "installable": True,
}
