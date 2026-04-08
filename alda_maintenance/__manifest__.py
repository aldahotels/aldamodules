# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# © 2026 Jose Luis Algara <osotranquilo@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Alda Maintenance",
    "version": "16.0.1.0.0",
    "summary": "Adds hotel (pms.property) field to maintenance equipment",
    "category": "Customizations",
    "author": (
        "Alexandra Suarez (Aldamodules), "
        "Jose Luis Algara (Aldamodules), "
        "Odoo Community Association (OCA)"
    ),
    "maintainer": "Alda hotels",
    "website": "https://github.com/OCA/pms",
    "license": "AGPL-3",
    "depends": [
        "maintenance",
        "pms",
    ],
    "data": [
        "views/maintenance_equipment_view.xml",
    ],
}
