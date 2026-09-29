# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)

RETENTION_PARAM = "alda_security_baseline.export_log_retention_days"
DEFAULT_RETENTION_DAYS = 180


class AldaSecurityExportLog(models.Model):
    _name = "alda.security.export.log"
    _description = "Data Export Log"
    _order = "export_date desc, id desc"
    _rec_name = "model_name"

    export_date = fields.Datetime(
        required=True,
        index=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    model_name = fields.Char(
        string="Model",
        required=True,
        index=True,
        readonly=True,
    )
    record_count = fields.Integer(string="Records", readonly=True)
    field_count = fields.Integer(string="Fields", readonly=True)
    import_compat = fields.Boolean(
        string="Import-Compatible",
        readonly=True,
        help="The export was requested in import-compatible mode.",
    )

    @api.model
    def _log_export(self, records, fields_to_export):
        """Record one ``export_data`` call made on ``records``.

        Grouped spreadsheet exports call ``export_data`` once per group within
        the same HTTP request: those calls are merged into a single row.
        """
        cache = self._get_request_cache()
        key = (records._name, tuple(fields_to_export))
        if cache is not None and key in cache:
            log = self.browse(cache[key]).exists()
            if log:
                log.record_count += len(records)
                return log
        log = self.create(
            {
                "user_id": self.env.uid,
                "model_name": records._name,
                "record_count": len(records),
                "field_count": len(fields_to_export),
                "import_compat": bool(self.env.context.get("import_compat")),
            }
        )
        if cache is not None:
            cache[key] = log.id
        return log

    @api.model
    def _get_request_cache(self):
        """Per-request storage of the rows created, or None outside HTTP."""
        if not request:
            return None
        cache = getattr(request, "_alda_security_export_logs", None)
        if cache is None:
            cache = request._alda_security_export_logs = {}
        return cache

    @api.model
    def _get_retention_days(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(RETENTION_PARAM, DEFAULT_RETENTION_DAYS)
        )
        try:
            return int(value)
        except (TypeError, ValueError):
            _logger.warning(
                "Invalid value %r for parameter %s, using %d days.",
                value,
                RETENTION_PARAM,
                DEFAULT_RETENTION_DAYS,
            )
            return DEFAULT_RETENTION_DAYS

    @api.autovacuum
    def _gc_export_logs(self):
        """Delete the rows older than the retention period (0 keeps all)."""
        days = self._get_retention_days()
        if days <= 0:
            return
        limit = fields.Datetime.now() - timedelta(days=days)
        self.sudo().search([("export_date", "<", limit)]).unlink()
