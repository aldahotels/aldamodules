import base64
import io
import logging
import re
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SpreadsheetCellMapping(models.Model):
    _name = "spreadsheet.cell.mapping"
    _description = "Mapeo de Celdas entre Hojas de Cálculo"
    name = fields.Char(string="Nombre", compute="_compute_name")
    central_file_id = fields.Many2one(
        "spreadsheet.central.file", string="Archivo Central", required=True
    )
    source_document_id = fields.Many2one(
        "documents.document", string="Documento Fuente", required=True
    )
    source_cell = fields.Char(
        string="Celda Fuente", required=True, help="Ej: A1, B2, etc."
    )
    target_cell = fields.Char(
        string="Celda Destino", required=True, help="Ej: A1, B2, etc."
    )
    last_value = fields.Char(string="Último valor sincronizado", readonly=True)
    active = fields.Boolean(string="Activo", default=True)

    @api.depends("source_document_id", "source_cell", "target_cell")
    def _compute_name(self):
        for mapping in self:
            source_name = mapping.source_document_id.name or "?"
            mapping.name = (
                f"{source_name} [{mapping.source_cell}] → [{mapping.target_cell}]"
            )

    @staticmethod
    def patch_xlsx_cell(binary_data, target_cell, new_value):
        in_memory_zip = io.BytesIO(binary_data)
        out_buffer = io.BytesIO()
        with zipfile.ZipFile(in_memory_zip, "r") as zin, zipfile.ZipFile(
            out_buffer, "w", compression=zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.namelist():
                file_data = zin.read(item)
                if item == "xl/worksheets/sheet1.xml":
                    xml_content = file_data.decode("utf-8")
                    pattern = (
                        r'(<c[^>]*r="' + re.escape(target_cell) + r'"[^>]*>)(.*?)(</c>)'
                    )

                    def repl(match):
                        cell_open = match.group(1)
                        new_v = f"<v>{new_value}</v>"
                        return cell_open + new_v + match.group(3)

                    xml_modified = re.sub(pattern, repl, xml_content, flags=re.DOTALL)
                    file_data = xml_modified.encode("utf-8")
                zout.writestr(item, file_data)
        return out_buffer.getvalue()

    def action_sync_now(self):
        self.ensure_one()
        if (
            not self.central_file_id.document_id.attachment_id
            or not self.source_document_id.attachment_id
        ):
            raise UserError(_("Uno de los documentos no tiene un archivo adjunto"))
        try:
            # Extraer el valor desde el documento fuente usando el método del archivo central.
            value = self.central_file_id._extract_cell_value(
                self.source_document_id, self.source_cell
            )
            central_doc = self.central_file_id.document_id
            central_binary = base64.b64decode(central_doc.attachment_id.datas)
            central_extension = self.central_file_id._get_file_extension(
                central_doc.name
            )
            if central_extension == ".xlsx":
                # Actualizar únicamente la celda especificada sin reescribir completamente el archivo.
                patched_binary = self.patch_xlsx_cell(
                    central_binary, self.target_cell, str(value)
                )
                # Actualizar el adjunto en Odoo con el nuevo contenido.
                central_doc.attachment_id.write(
                    {"datas": base64.b64encode(patched_binary)}
                )
                self.write({"last_value": str(value)})
            else:
                raise UserError(
                    _(
                        "Formato de archivo no soportado para el archivo central. Use XLSX."
                    )
                )
        except Exception as e:
            raise UserError(_("Error al sincronizar: %s") % str(e))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sincronización completada"),
                "message": _("El valor ha sido sincronizado correctamente."),
                "sticky": False,
                "type": "success",
            },
        }
