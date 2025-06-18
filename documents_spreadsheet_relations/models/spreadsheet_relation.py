import base64
import io
import logging

import pandas as pd
import xlrd

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SpreadsheetRelationWizard(models.TransientModel):
    _name = "spreadsheet.relation.wizard"
    _description = "Asistente para relacionar hojas de cálculo"

    document_id = fields.Many2one(
        "documents.document", string="Document", required=True
    )
    document_name = fields.Char(
        string="Nombre del documento", help="Nombre del documento Excel a relacionar"
    )
    relation_key = fields.Char(
        string="Valor de relación",
        help="Valor del campo común para relacionar con otras hojas de cálculo",
    )
    extract_from_cell = fields.Boolean(
        string="Extraer de celda",
        help="Extraer el valor de relación de una celda específica",
    )
    cell_coordinate = fields.Char(
        string="Coordenada de celda", help="Ejemplo: A1, B2, etc."
    )

    @api.onchange("document_id")
    def _onchange_document_id(self):
        if self.document_id:
            self.relation_key = self.document_id.relation_key
            self.document_name = self.document_id.name

    @api.onchange("document_name")
    def _onchange_document_name(self):
        if self.document_name:
            # Buscar documentos que coincidan con el nombre
            documents = self.env["documents.document"].search(
                [("name", "ilike", self.document_name)], limit=1
            )
            if documents:
                self.document_id = documents[0].id
                self.relation_key = documents[0].relation_key

    @api.model
    def default_get(self, fields_list):
        """Precompletar valores por defecto, especialmente document_id desde el contexto"""
        res = super().default_get(fields_list)

        _logger.info("Context en default_get: %s", self.env.context)

        # Obtener el ID del documento activo desde el contexto
        active_id = self.env.context.get("active_id")
        _logger.info(f"Activar ID {active_id}")
        default_document_id = self.env.context.get("default_document_id")

        # Usar cualquiera de los dos valores disponibles
        document_id = active_id or default_document_id

        _logger.info("Document ID: %s", document_id)

        if document_id:
            document = self.env["documents.document"].browse(document_id)
            res["document_id"] = document.id
            res["document_name"] = document.name
            # También precompletar el valor de relación si existe
            if document.relation_key:
                res["relation_key"] = document.relation_key

            _logger.info("Document encontrado: %s (ID: %s)", document.name, document.id)

        _logger.info("Valores por defecto: %s", res)

        return res

    def action_extract_and_save(self):
        self.ensure_one()

        # Si tenemos document_name pero no document_id, intentar encontrar el documento
        if not self.document_id and self.document_name:
            documents = self.env["documents.document"].search(
                [("name", "ilike", self.document_name)], limit=1
            )
            if documents:
                self.document_id = documents[0].id

        # Si aún no tenemos document_id pero tenemos active_id, usarlo
        if not self.document_id and self._context.get("active_id"):
            self.document_id = self.env["documents.document"].browse(
                self._context.get("active_id")
            )

        if not self.document_id:
            raise UserError(
                _("Debe seleccionar un documento o ingresar un nombre válido")
            )

        if self.extract_from_cell and self.cell_coordinate:
            # Extraer valor de la celda especificada
            value = self._extract_cell_value()
            if value:
                self.relation_key = value

        # Guardar el valor de relación en el documento
        if self.relation_key:
            self.document_id.write({"relation_key": self.relation_key})
            # Buscar documentos relacionados
            self.document_id.find_related_spreadsheets()

        _logger.info(f" aqui se imprime {self}")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Relación configurada"),
                "message": _(
                    "El valor de relación ha sido configurado correctamente para el documento %s."
                )
                % self.document_id.name,
                "sticky": False,
                "type": "success",
            },
        }

    def _extract_cell_value(self):
        """Extrae el valor de una celda específica de la hoja de cálculo"""
        self.ensure_one()

        if not self.document_id.attachment_id:
            raise UserError(_("El documento no tiene un archivo adjunto"))

        try:
            # Obtener el contenido del archivo
            binary_content = base64.b64decode(self.document_id.attachment_id.datas)
            file_extension = self._get_file_extension(self.document_id.name)

            # Procesamiento diferente según el tipo de archivo
            if file_extension == ".xlsx":
                return self._extract_from_xlsx_pandas(binary_content)
            elif file_extension == ".xls":
                return self._extract_from_xls(binary_content)
            else:
                raise UserError(
                    _(
                        "Formato de archivo no soportado. Solo se admiten archivos XLS y XLSX."
                    )
                )

        except Exception as e:
            raise UserError(_("Error al extraer el valor de la celda: %s") % str(e))

    def _get_file_extension(self, filename):
        """Obtiene la extensión del archivo"""
        if not filename:
            return ""
        return "." + filename.split(".")[-1].lower() if "." in filename else ""

    def _extract_from_xlsx_pandas(self, binary_content):
        """Extrae el valor de una celda de un archivo XLSX usando pandas"""
        try:
            # Cargar el archivo en memoria
            file_stream = io.BytesIO(binary_content)

            # Leer el archivo con pandas
            df = pd.read_excel(file_stream, engine="openpyxl")

            # Analizar la coordenada de la celda (ej: A1, B2)
            col_letter = self.cell_coordinate[0].upper()
            col_index = ord(col_letter) - ord("A")
            row_index = int(self.cell_coordinate[1:]) - 1

            # Verificar si los índices están dentro de los límites
            if row_index >= len(df) or col_index >= len(df.columns):
                raise UserError(
                    _(
                        "La coordenada de celda está fuera de los límites de la hoja de cálculo."
                    )
                )

            # Obtener el valor de la celda
            cell_value = df.iloc[row_index, col_index]

            return str(cell_value) if not pd.isna(cell_value) else ""
        except Exception as e:
            raise UserError(_("Error al leer el archivo XLSX: %s") % str(e))

    def _extract_from_xls(self, binary_content):
        """Extrae el valor de una celda de un archivo XLS usando xlrd"""
        try:
            # Abrir el archivo con xlrd
            workbook = xlrd.open_workbook(file_contents=binary_content)
            sheet = workbook.sheet_by_index(0)  # Primera hoja

            # Analizar la coordenada de la celda (ej: A1, B2)
            col = ord(self.cell_coordinate[0].upper()) - ord("A")
            row = int(self.cell_coordinate[1:]) - 1

            # Verificar si los índices están dentro de los límites
            if row >= sheet.nrows or col >= sheet.ncols:
                raise UserError(
                    _(
                        "La coordenada de celda está fuera de los límites de la hoja de cálculo."
                    )
                )

            # Obtener el valor de la celda
            cell_value = sheet.cell_value(row, col)

            return str(cell_value) if cell_value is not None else ""
        except Exception as e:
            raise UserError(_("Error al leer el archivo XLS: %s") % str(e))
