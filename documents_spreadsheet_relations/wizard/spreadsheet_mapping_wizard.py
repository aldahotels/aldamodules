from odoo import api, fields, models


# Wizar para mapear los campos
class SpreadsheetMappingWizard(models.TransientModel):
    _name = "spreadsheet.mapping.wizard"
    _description = "Añadir Mapeo de Celdas"

    central_file_id = fields.Many2one(
        "spreadsheet.central.file", string="Archivo Central", required=True
    )
    source_document_id = fields.Many2one(
        "documents.document", string="Documento Fuente", required=True
    )
    source_document_name = fields.Char(string="Buscar documento fuente")
    source_cell = fields.Char(
        string="Celda Fuente", required=True, help="Ej: A1, B2, etc."
    )
    target_cell = fields.Char(
        string="Celda Destino", required=True, help="Ej: A1, B2, etc."
    )

    @api.onchange("source_document_name")
    def _onchange_source_document_name(self):
        if self.source_document_name:
            documents = self.env["documents.document"].search(
                [("name", "ilike", self.source_document_name)], limit=1
            )
            if documents:
                self.source_document_id = documents[0].id

    def action_add_mapping(self):
        self.ensure_one()
        mapping = self.env["spreadsheet.cell.mapping"].create(
            {
                "central_file_id": self.central_file_id.id,
                "source_document_id": self.source_document_id.id,
                "source_cell": self.source_cell,
                "target_cell": self.target_cell,
            }
        )
        # Sincronizar inmediatamente
        mapping.action_sync_now()
        return {
            "type": "ir.actions.act_window",
            "res_model": "spreadsheet.central.file",
            "res_id": self.central_file_id.id,
            "view_mode": "form",
            "target": "current",
        }
