# Copyright 2018-2022 Jose Luis Algara Toledo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "PMS Data Bi",
    "summary": "Export hotel data for business intelligence",
    "version": "14.0.3.1.0",
    "license": "AGPL-3",
    "author": "Jose Luis Algara (Alda hotels) <osotranquilo@gmail.com>, "
    "Odoo Community Association (OCA)",
    "website": "https://github.com/OsoTranquilo/aldahotels.git",
    "depends": ["pms", "pms_l10n_es"],
    "category": "Generic Modules/Property Management System",
    "data": [
        "views/budget.xml",
        "views/inherit_pms_property.xml",
        "views/inherit_res_users.xml",
        "views/inherit_res_partners.xml",
        "security/data_bi.xml",
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
}
