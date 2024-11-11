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
    "name": "Custom POS PMS Link",
    "summary": "Allows to access directly to the POS",
    "version": "14.0.1.0.0",
    "author": "Comunitea Servicios Tecnológicos S.L.",
    "website": "www.comunitea.com",
    "license": "AGPL-3",
    "category": "Custom",
    "depends": [
        "portal",
        "point_of_sale",
        "auth_signup",
        "custom_login_by_token",
    ],
    "data": [
        "data/ir_module_category_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [],
    },
    "installable": True,
}
