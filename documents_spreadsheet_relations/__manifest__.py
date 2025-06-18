{
    "name": "Document Spreadsheet Relations and Sync",
    "version": "16.0.1.0.0",
    "category": "Documents",
    "summary": "Vincular y sincronizar hojas de cálculo mediante celdas específicas",
    "author": "Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>, Odoo Community Association (OCA)",
    "depends": ["documents", "spreadsheet"],
    "external_dependencies": {
        "python": ["openpyxl"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/wizard_views.xml",
        "views/spreadsheet_relation_views.xml",
        "views/documents_views.xml",
        "views/spreadsheet_central_file_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "documents_spreadsheet_relations/static/src/js/spreadsheet_relation.js",
        ],
        "web.assets_qweb": [
            "documents_spreadsheet_relations/static/src/xml/spreadsheet_relation_templates.xml",
        ],
    },
    "website": "https://github.com/OCA/pms",
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
