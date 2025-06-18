import base64
import datetime
import io
import logging

import openpyxl
import xlrd

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SpreadsheetCentralFile(models.Model):
    _name = "spreadsheet.central.file"
    _description = "Archivo Excel Central"

    name = fields.Char(string="Nombre", required=True)
    document_id = fields.Many2one(
        "documents.document", string="Documento", required=True
    )
    mapping_ids = fields.One2many(
        "spreadsheet.cell.mapping", "central_file_id", string="Mapeos de celdas"
    )
    last_sync = fields.Datetime(string="Última sincronización")

    def action_sync_values(self):
        """Sincroniza todos los valores de los archivos fuente al archivo central"""
        self.ensure_one()

        if not self.document_id.attachment_id:
            raise UserError(_("El archivo central no tiene un adjunto"))

        # Cargar el archivo central
        central_binary = base64.b64decode(self.document_id.attachment_id.datas)
        central_extension = self._get_file_extension(self.document_id.name)

        if central_extension == ".xlsx":
            if not openpyxl:
                raise UserError(
                    _(
                        "La biblioteca openpyxl no está instalada. Por favor, instálela para usar esta función."
                    )
                )

            central_buffer = io.BytesIO(central_binary)
            central_workbook = openpyxl.load_workbook(central_buffer)
            central_sheet = central_workbook.active

            for mapping in self.mapping_ids.filtered(lambda m: m.active):
                try:
                    value = self._extract_cell_value(
                        mapping.source_document_id, mapping.source_cell
                    )

                    target_cell = self._parse_cell_coordinate(mapping.target_cell)
                    central_sheet[target_cell] = value

                    mapping.write({"last_value": str(value)})
                except Exception as e:
                    _logger.error(
                        "Error al sincronizar mapeo %s: %s", mapping.name, str(e)
                    )

            output = io.BytesIO()
            central_workbook.save(output)
            binary_data = output.getvalue()

            self.document_id.attachment_id.write(
                {"datas": base64.b64encode(binary_data)}
            )

        elif central_extension == ".xls":
            raise UserError(
                _("El formato XLS no está soportado para el archivo central. Use XLSX.")
            )
        else:
            raise UserError(
                _("Formato de archivo no soportado para el archivo central. Use XLSX.")
            )

        # Actualizar fecha de última sincronización
        self.write({"last_sync": fields.Datetime.now()})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sincronización completada"),
                "message": _(
                    "Los valores han sido sincronizados correctamente al archivo central."
                ),
                "sticky": False,
                "type": "success",
            },
        }

    def _get_file_extension(self, filename):
        if not filename:
            return ""
        return "." + filename.split(".")[-1].lower() if "." in filename else ""

    def _extract_cell_value(self, document, cell_coordinate):
        if not document.attachment_id:
            raise UserError(_("El documento no tiene un archivo adjunto"))

        binary_content = base64.b64decode(document.attachment_id.datas)
        file_extension = self._get_file_extension(document.name)

        if file_extension == ".xlsx":
            return self._extract_from_xlsx(binary_content, cell_coordinate)
        elif file_extension == ".xls":
            return self._extract_from_xls(binary_content, cell_coordinate)
        else:
            raise UserError(
                _("Formato de archivo no soportado. Solo se admiten XLS y XLSX.")
            )

    def _extract_from_xlsx(self, binary_content, cell_coordinate):
        try:
            if not openpyxl:
                raise UserError(
                    _(
                        "La biblioteca openpyxl no está instalada. Por favor, instálela para usar esta función."
                    )
                )

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

    def _extract_from_xls(self, binary_content, cell_coordinate):
        try:
            workbook = xlrd.open_workbook(file_contents=binary_content)
            sheet = workbook.sheet_by_index(0)  # Primera hoja

            col_letter = cell_coordinate[0].upper()
            col = ord(col_letter) - ord("A")
            row = int(cell_coordinate[1:]) - 1

            if row >= sheet.nrows or col >= sheet.ncols:
                raise UserError(
                    _(
                        "La coordenada de celda está fuera de los límites de la hoja de cálculo."
                    )
                )

            # Obtener el valor de la celda
            cell_value = sheet.cell_value(row, col)

            return cell_value
        except Exception as e:
            raise UserError(_("Error al leer el archivo XLS: %s") % str(e))

    def _parse_cell_coordinate(self, coordinate):
        return coordinate
