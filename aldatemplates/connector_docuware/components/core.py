# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.component.core import AbstractComponent


class BaseDocuwareConnectorComponent(AbstractComponent):
    """Base Docuware Connector Component
    All components of this connector should inherit from it.
    """

    _name = "base.docuware.connector"
    _inherit = "base.connector"
    _collection = "docuware.backend"
