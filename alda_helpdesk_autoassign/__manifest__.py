##############################################################################
#    License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
#    Copyright (C) 2025 Consultores Hoteleros Integrales Alda Hotels All Rights Reserved
#    Jose Luis Algara Toledo <informatica@aldahotels.com>
#    Irlui Tupac Ramírez Hernández <irlui@aldahotels.com>
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
    "name": "Helpdesk Alda Auto-assign by Property",
    "summary": "Autoassign tickets to employees based on their job positions",
    "version": "16.0.1.0.0",
    "author": "Odoo Community Association (OCA),"
    "Irlui Ramirez (Alda Hotels), Jose Luis Algara (Alda Hotels)",
    "website": "https://github.com/OCA/pms",
    "license": "LGPL-3",
    "depends": ["helpdesk", "alda_helpdesk_pms", "helpdesk_hr"],
    "category": "PMS",
    "data": [
        "views/helpdesk_ticket_views.xml",
    ],
    "assets": {},
    "installable": True,
    "application": True,
}
