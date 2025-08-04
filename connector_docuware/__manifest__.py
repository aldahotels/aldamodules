# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Connector Docuware",
    "version": "16.0.1.0.0",
    "summary": "",
    "category": "",
    "author": "Comunitea , Odoo Community Association (OCA)",
    "maintainer": "Comunitea",
    "website": "https://github.com/OCA/pms",
    "license": "AGPL-3",
    "depends": [
        "account",
        "connector",
        "pms",
        "account_payment_partner",
        "account_asset",
        "onchange_helper",
    ],
    "data": [
        "views/docuware_backend.xml",
        "views/docuware_cabinet.xml",
        "views/account_move.xml",
        "security/ir.model.access.csv",
    ],
}
