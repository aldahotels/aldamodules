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
    "name": "POS partner limit",
    "summary": "Limits the partners loaded in the POS",
    "version": "14.0.1.0.0",
    "author": "Comunitea Servicios Tecnológicos S.L.",
    "website": "https://comunitea.com",
    "license": "AGPL-3",
    "category": "Point of Sale",
    "depends": [
        "point_of_sale",
        "pms",
    ],
    "data": [
        "views/assets_common.xml",
    ],
    "demo": [],
    "qweb": [],
    "installable": True,
}
