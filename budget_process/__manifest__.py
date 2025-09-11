# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Budget Process",
    "version": "16.0.1.0.0",
    "author": "Alexandra Suarez (Alda), Odoo Community Association (OCA)",
    "license": "LGPL-3",
    "category": "Accounting",
    "summary": "Module for hotel budget process",
    "website": "https://github.com/OCA/pms",
    "depends": ["base", "pms", "account", "account_accountant", "pms_data_bi"],
    "images": ["static/description/icon.png"],
    "data": [
        "security/budget_groups.xml",
        "security/ir.model.access.csv",
        "data/user_access_rules.xml",
        "views/budget_hotel_views.xml",
        "views/budget_capex_views.xml",
        "views/budget_cfo_views.xml",
        "views/budget_controller.xml",
        "views/budget_fb_views.xml",
        "views/budget_informatica_views.xml",
        "views/budget_marketing_views.xml",
        "views/budget_operaciones_views.xml",
        "views/budget_revenue_views.xml",
        "views/budget_rn_views.xml",
        "views/budget_taz_views.xml",
        "views/budget_data_views.xml",
        "wizard/budget_load_wizard_views.xml",
    ],
    "installable": True,
    "application": True,
}
