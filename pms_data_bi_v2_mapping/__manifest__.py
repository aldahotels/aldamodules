# Copyright 2018-2022 Jose Luis Algara Toledo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "PMS Data Bi Mapper V11.0",
    "summary": "Export hotel data for business intelligence mapping V11 instance",
    "version": "14.0.3.1.0",
    "license": "AGPL-3",
    "author": "Jose Luis Algara (Alda hotels) <osotranquilo@gmail.com>, "
    "Odoo Community Association (OCA)",
    "website": "https://github.com/OsoTranquilo/aldahotels.git",
    "depends": ["pms", "pms_l10n_es", "pms_data_bi", "migrated_hotel"],
    "category": "Generic Modules/Property Management System",
    "data": [
        "views/migrated_hotel_views.xml",
        "data/ir_cron.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
}
