{
    "name": "Connector Agora",
    "version": "16.0.1.0.0",
    "summary": "Connector for Agora POS - Import sales invoices",
    "category": "Connector",
    "author": (
        "Alexandra Suarez (Aldamodules), "
        "Jose Luis Algara (Aldamodules), "
        "Odoo Community Association (OCA)"
    ),
    "maintainer": "Alda",
    "website": "https://github.com/OCA/pms",
    "license": "AGPL-3",
    "depends": [
        "account",
        "connector",
        "pms",
        "account_payment_partner",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/agora_import_wizard.xml",
        "views/agora_backend.xml",
        "views/account_move.xml",
    ],
    "demo": ["demo/agora_backend.xml"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
