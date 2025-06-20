from odoo import _, api, fields, models


class Document(models.Model):
    _inherit = "documents.document"

    # Almacenar el valor de relación
    relation_key = fields.Char(
        string="Relationship field", help="Common value to relate to other spreadsheets"
    )

    # determinar si es una hoja de cálculo
    is_spreadsheet = fields.Boolean(
        string="Es hoja de cálculo",
        compute="_compute_is_spreadsheet",
        store=True,
        help="Indica si este documento es una hoja de cálculo",
    )

    # Campo calculado para contar documentos relacionados
    related_spreadsheet_count = fields.Integer(
        string="Documentos relacionados",
        compute="_compute_related_spreadsheet_count",
        help="Número de hojas de cálculo relacionadas",
    )

    @api.depends("mimetype", "handler", "raw")
    def _compute_is_spreadsheet(self):
        for document in self:
            spreadsheet_mimetypes = [
                "application/vnd.ms-excel",  # XLS
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # XLSX
                "application/vnd.oasis.opendocument.spreadsheet",  # ODS
                "text/csv",  # CSV
                "application/vnd.ms-excel.sheet.macroEnabled.12",  # XLSM
                "application/o-spreadsheet",  # MIMEtype odoo
            ]

            document.is_spreadsheet = (
                document.mimetype in spreadsheet_mimetypes
                or document.handler == "spreadsheet"
                or (document.mimetype == "application/o-spreadsheet" and document.raw)
            )

    # Calcula el número de hojas de cálculo relacionadas
    def _compute_related_spreadsheet_count(self):
        for document in self:
            if document.relation_key:
                document.related_spreadsheet_count = self.search_count(
                    [
                        ("id", "!=", document.id),
                        ("relation_key", "=", document.relation_key),
                        ("relation_key", "!=", False),
                    ]
                )
            else:
                document.related_spreadsheet_count = 0

    def find_related_spreadsheets(self):
        self.ensure_one()
        if not self.relation_key:
            return

        self._compute_related_spreadsheet_count()

        # Notificar al usuario que se encontraron documentos relacionados
        if self.related_spreadsheet_count > 0:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Documentos relacionados"),
                    "message": _("Se encontraron %s documentos relacionados.")
                    % self.related_spreadsheet_count,
                    "sticky": False,
                    "type": "success",
                },
            }
        else:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Documentos relacionados"),
                    "message": _("No se encontraron documentos relacionados."),
                    "sticky": False,
                    "type": "warning",
                },
            }

    def action_view_related_spreadsheets(self):
        self.ensure_one()
        if not self.relation_key:
            return

        # Buscar documentos relacionados
        related_docs = self.search(
            [
                ("id", "!=", self.id),
                ("relation_key", "=", self.relation_key),
                ("relation_key", "!=", False),
            ]
        )

        # Crear acción para mostrar los documentos relacionados
        action = {
            "name": _("Documentos relacionados"),
            "type": "ir.actions.act_window",
            "res_model": "documents.document",
            "view_mode": "kanban,tree,form",
            "domain": [("id", "in", related_docs.ids)],
            "context": {"create": False},
        }

        return action
