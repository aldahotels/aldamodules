from odoo import api, fields, models


# Wizar para crear el archivo central de los presupuestos
class SpreadsheetCentralFileWizard(models.TransientModel):
    _name = "spreadsheet.central.file.wizard"
    _description = "Configurar Archivo Central"

    document_id = fields.Many2one(
        "documents.document", string="Documento", required=True
    )
    name = fields.Char(string="Nombre", required=True)

    @api.onchange("document_id")
    def _onchange_document_id(self):
        if self.document_id:
            self.name = self.document_id.name

    def action_create_central_file(self):
        self.ensure_one()
        central_file = self.env["spreadsheet.central.file"].create(
            {
                "name": self.name,
                "document_id": self.document_id.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "spreadsheet.central.file",
            "res_id": central_file.id,
            "view_mode": "form",
            "target": "current",
        }
