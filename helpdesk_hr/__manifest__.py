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
    "name": "Alda Helpdesk HR",
    "summary": "Asociate job positions with helpdesk teams",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Odoo Community Association (OCA),"
    "Jose Luis Algara (Alda Hotels), Irlui Ramirez (Alda Hotels)",
    "depends": ["helpdesk", "hr", "alda_helpdesk_pms"],
    "website": "https://github.com/OCA/pms",
    "category": "Helpdesk",
    "data": [
        "views/hr_job_views.xml",
    ],
    "assets": {},
    "installable": True,
    "application": True,
}
