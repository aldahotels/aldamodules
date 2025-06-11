# Copyright Alda Hotels 2025 Jose Luis Algara Toledo
# Copyright Alda Hotels 2025 Irlui Ramirez (irluidev)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Helpdesk PMS Alda",
    "summary": "Create tickets related with the property",
    "version": "16.0.1.0.0",
    "author": "Odoo Community Association (OCA),"
    "Irlui Ramirez (Alda Hotels), Jose Luis Algara (Alda Hotels)",
    "website": "https://github.com/aldahotels/aldamodules.git",
    "license": "LGPL-3",
    "depends": ["website", "helpdesk", "helpdesk_pms_enterprise"],
    "category": "PMS",
    "data": [
        "data/helpdesk_ticket_class_data.xml",
        "security/ir.model.access.csv",
        "views/actions.xml",
        "views/helpdesk_ticket_class_views.xml",
        "views/helpdesk_ticket_type_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/helpdesk_pms_form_template.xml",
    ],
    "assets": {},
    "installable": True,
    "application": True,
}
