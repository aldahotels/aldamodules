# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from base64 import b64decode

from werkzeug.exceptions import BadRequest, Unauthorized

from odoo import http

DOCUMENT_TYPES = {
    "Factura": "docuware.account.move",
    "Ticket - Otros gastos": "docuware.account.move",
}


class DocuwareWebhookController(http.Controller):
    @http.route(
        "/new_document", type="json", auth="public", methods=["POST"], csrf=False
    )
    def new_document(self):
        """
        webhook al que se llama desde docuware al archivar un nuevo documento.
        {
            "document_id": X,
            "cabinet_id": "XXXX-XXXX-XXXX-XXXX-XXXX",
            "type": "Factura" /* Factura o Ticket - Otros gastos */
        }
        """
        auth_header = http.request.httprequest.headers.get("Authorization", "")
        if not auth_header:
            raise Unauthorized("Wrong authentication")
        auth_token = auth_header.strip().split(" ")
        if len(auth_token) > 1:
            auth_token = auth_token[1]
        username, password = b64decode(auth_token).decode().split(":", 1)
        backend = (
            http.request.env["docuware.backend"]
            .sudo()
            .search(
                [
                    ("webhook_user", "=", username),
                    ("webhook_password", "=", password),
                ]
            )
        )
        if not backend:
            raise Unauthorized("Wrong authentication")
        document_data = http.request.jsonrequest
        document_id = document_data.get("document_id")
        cabinet_id = document_data.get("cabinet_id")
        document_type = document_data.get("type")
        if document_type not in DOCUMENT_TYPES.keys():
            raise BadRequest("Wrong type value")
        backend.with_user(backend.execute_user_id).import_docuware_document(
            cabinet_id, document_id, DOCUMENT_TYPES[document_type]
        )
        return True
