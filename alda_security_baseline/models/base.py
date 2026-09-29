# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class Base(models.AbstractModel):
    _inherit = "base"

    def export_data(self, fields_to_export):
        res = super().export_data(fields_to_export)
        self._alda_log_export(fields_to_export)
        return res

    def _alda_log_export(self, fields_to_export):
        """Log a successful export. Never breaks the export."""
        try:
            with self.env.cr.savepoint():
                self.env["alda.security.export.log"].sudo()._log_export(
                    self, fields_to_export
                )
        except Exception:
            _logger.exception("Could not log the export of %s records.", self._name)
