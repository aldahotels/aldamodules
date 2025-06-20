# Copyright Alda Hotels 2025 Jose Luis Algara Toledo
# Copyright Alda Hotels 2025 Irlui Ramirez (irluidev)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Helpdesk PMS Entreprise",
    "summary": "Create tickets related with the property",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Odoo Community Association (OCA),"
    "Jose Luis Algara (Alda Hotels), Irlui Ramirez (Alda Hotels)",
    "depends": ["helpdesk", "pms", "hr", "pms_hr_property"],
    "website": "https://github.com/OCA/pms",
    "category": "PMS",
    "data": [
        "views/actions.xml",
        "views/pms_property_views.xml",
        "views/helpdesk_ticket_views.xml",
    ],
    "assets": {},
    "installable": True,
    "application": True,
}
