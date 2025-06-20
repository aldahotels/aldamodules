import base64
import datetime
import io
import json
import logging
import re

import openpyxl
import xlrd

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SpreadsheetCentralFile(models.Model):
    _name = "spreadsheet.central.file"
    _description = "Archivo Excel Central o Archivo Clonado"
    name = fields.Char(string="Nombre", required=True)
    document_id = fields.Many2one(
        "documents.document", string="Documento", required=True
    )
    mapping_ids = fields.One2many(
        "spreadsheet.cell.mapping", "central_file_id", string="Mapeos de celdas"
    )
    last_sync = fields.Datetime(string="Última sincronización")

    # Método para sincronizar cada uno de los mapeos activos con el archivo central.
    def action_sync_values(self):
        self.ensure_one()
        if not self.document_id.attachment_id:
            raise UserError(_("El archivo central no tiene un adjunto"))
        central_binary = base64.b64decode(self.document_id.attachment_id.datas)
        central_extension = self._get_file_extension(self.document_id.name)
        if central_extension == ".xlsx":
            self._sync_xlsx(central_binary)
        elif self._is_clone(central_binary):
            self._sync_clone(central_binary)
        else:
            raise UserError(_("Formato de archivo no soportado para el archivo central. Use XLSX o el formato clonado."))
        self.write({"last_sync": fields.Datetime.now()})
        return self._get_success_notification()
    def _is_clone(self, central_binary):
        try:
            json_str = central_binary.decode("utf-8")
            data = json.loads(json_str)
            return "xl/worksheets/sheet1.xml" in data
        except Exception:
            return False
    def _sync_clone(self, central_binary):
        try:
            json_str = central_binary.decode("utf-8")
            data = json.loads(json_str)
            xml_content = data.get("xl/worksheets/sheet1.xml", "")
            for mapping in self.mapping_ids.filtered(lambda m: m.active):
                self._sync_mapping_clone(mapping, xml_content)
            data["xl/worksheets/sheet1.xml"] = xml_content
            self._write_attachment(data)
        except Exception as e:
            raise UserError(_("Error al sincronizar archivo clonado: %s") % str(e))
    def _sync_mapping_clone(self, mapping, xml_content):
        try:
            value = self._extract_cell_value(mapping.source_document_id, mapping.source_cell)
            pattern = r'(<c[^>]*r="' + re.escape(mapping.target_cell) + r'"[^>]*>)(.*?)(</c>)'
            xml_content = re.sub(pattern, lambda match: match.group(1) + f"<v>{value}</v>" + match.group(3), xml_content, flags=re.DOTALL)
            mapping.write({"last_value": str(value)})
        except Exception as e:
            _logger.error("Error al sincronizar mapeo %s: %s", mapping.name, str(e))
    def _sync_xlsx(self, central_binary):
        if not openpyxl:
            raise UserError(_("La biblioteca openpyxl no está instalada."))
        try:
            central_buffer = io.BytesIO(central_binary)
            central_workbook = openpyxl.load_workbook(central_buffer)
            central_sheet = central_workbook.active
            for mapping in self.mapping_ids.filtered(lambda m: m.active):
                self._sync_mapping_xlsx(mapping, central_sheet)
            self._write_xlsx_attachment(central_workbook)
        except Exception as e:
            raise UserError(_("Error al sincronizar archivo XLSX: %s") % str(e))
    def _sync_mapping_xlsx(self, mapping, central_sheet):
        try:
            value = self._extract_cell_value(mapping.source_document_id, mapping.source_cell)
            target_cell = self._parse_cell_coordinate(mapping.target_cell)
            central_sheet[target_cell] = value
            mapping.write({"last_value": str(value)})
        except Exception as e:
            _logger.error("Error al sincronizar mapeo %s: %s", mapping.name, str(e))
    def _write_attachment(self, data):
        new_json = json.dumps(data)
        binary_data = new_json.encode("utf-8")
        self.document_id.attachment_id.write({"datas": base64.b64encode(binary_data)})
    def _write_xlsx_attachment(self, central_workbook):
        output = io.BytesIO()
        central_workbook.save(output)
        binary_data = output.getvalue()
        self.document_id.attachment_id.write({"datas": base64.b64encode(binary_data)})
    def _get_success_notification(self):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sincronización completada"),
                "message": _("Los valores han sido sincronizados correctamente al archivo central."),
                "sticky": False,
                "type": "success",
            },
        }

    # Función auxiliar para obtener la extensión del archivo a partir del nombre.
    def _get_file_extension(self, filename):
        if not filename:
            return ""
        return "." + filename.split(".")[-1].lower() if "." in filename else ""

    # extraer el valor de la celda desde el documento fuente.
    def _extract_cell_value(self, document, cell_coordinate):
        if not document.attachment_id:
            raise UserError(_("El documento no tiene un archivo adjunto"))
        binary_content = base64.b64decode(document.attachment_id.datas)
        try:
            json_str = binary_content.decode("utf-8")
            data = json.loads(json_str)
            if "xl/worksheets/sheet1.xml" in data:
                return self._extract_from_o_spreadsheet(binary_content, cell_coordinate)
        except Exception as e:
            _logger.info("No se interpretó como JSON: %s", e)
        file_extension = self._get_file_extension(document.name)
        if file_extension == ".xlsx":
            return self._extract_from_xlsx(binary_content, cell_coordinate)
        elif file_extension == ".xls":
            return self._extract_from_xls(binary_content, cell_coordinate)
        else:
            raise UserError(
                _(
                    "Formato de archivo no soportado. Solo se admiten XLS, XLSX o el formato clonado."
                )
            )

    # Método para extraer el valor de la celda de un archivo XLSX
    def _extract_from_xlsx(self, binary_content, cell_coordinate):
        try:
            if not openpyxl:
                raise UserError(_("La biblioteca openpyxl no está instalada."))
            file_stream = io.BytesIO(binary_content)
            try:
                workbook = openpyxl.load_workbook(file_stream, data_only=False)
            except Exception as e:
                _logger.warning(
                    "Error al cargar workbook con data_only=True: %s", str(e)
                )
                file_stream.seek(0)
                workbook = openpyxl.load_workbook(file_stream)
            if not workbook.sheetnames:
                raise UserError(_("El archivo Excel no contiene hojas."))
            sheet = workbook.active
            try:
                cell = self._parse_cell_coordinate(cell_coordinate)
                if cell not in sheet:
                    row, col = openpyxl.utils.coordinate_to_tuple(cell)
                    if row > sheet.max_row or col > sheet.max_column:
                        return None
                cell_value = sheet[cell].value
                if isinstance(cell_value, datetime.datetime):
                    cell_value = cell_value.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(cell_value, datetime.date):
                    cell_value = cell_value.strftime("%Y-%m-%d")
                return cell_value
            except Exception as e:
                _logger.error(
                    "Error al acceder a la celda %s: %s", cell_coordinate, str(e)
                )
                raise UserError(
                    _("No se pudo acceder a la celda %(cell_coordinate)s: %(error)s")
                    % {"cell_coordinate": cell_coordinate, "error": str(e)}
                )
        except Exception as e:
            _logger.error("Error al leer el archivo XLSX: %s", str(e))
            raise UserError(_("Error al leer el archivo XLSX: %s") % str(e))

    # Método para extraer el valor de una celda desde el contenido JSON (archivo clonado)
    def _extract_from_o_spreadsheet(self, binary_content, cell_coordinate):
        try:
            json_str = binary_content.decode("utf-8")
            data = json.loads(json_str)
            xml_content = data.get("xl/worksheets/sheet1.xml")
            if not xml_content:
                raise UserError(
                    _("No se encontró la hoja 'sheet1.xml' en el documento clonado.")
                )
            pattern = r'<c[^>]*r="' + re.escape(cell_coordinate) + r'"[^>]*>(.*?)</c>'
            match = re.search(pattern, xml_content, flags=re.DOTALL)
            if match:
                inner = match.group(1)
                v_match = re.search(r"<v>(.*?)</v>", inner, flags=re.DOTALL)
                return v_match.group(1) if v_match else None
            else:
                return None
        except Exception as e:
            raise UserError(_("Error al leer el documento clonado: %s") % str(e))

    # extraer el valor de una celda desde un archivo XLS
    def _extract_from_xls(self, binary_content, cell_coordinate):
        try:
            workbook = xlrd.open_workbook(file_contents=binary_content)
            sheet = workbook.sheet_by_index(0)
            col_letter = cell_coordinate[0].upper()
            col = ord(col_letter) - ord("A")
            row = int(cell_coordinate[1:]) - 1
            if row >= sheet.nrows or col >= sheet.ncols:
                raise UserError(
                    _(
                        "La coordenada de celda está fuera de los límites de la hoja de cálculo."
                    )
                )
            return sheet.cell_value(row, col)
        except Exception as e:
            raise UserError(_("Error al leer el archivo XLS: %s") % str(e))

    # Método auxiliar para parsear la coordenada (se puede extender si es necesario)
    def _parse_cell_coordinate(self, coordinate):
        return coordinate
