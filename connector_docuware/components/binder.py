# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.addons.component.core import Component


class DocuwareModelBinder(Component):
    _name = "docuware.binder"
    _inherit = ["base.binder", "base.docuware.connector"]
    _external_field = "docuware_id"

    _apply_on = [
        "docuware.cabinet",
        "docuware.account.move",
    ]
