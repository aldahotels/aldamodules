# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import date, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AgoraImportWizard(models.TransientModel):
    """Wizard to manually import invoices from Agora for a specific date range."""

    _name = "agora.import.wizard"
    _description = "Agora Manual Import Wizard"

    backend_id = fields.Many2one(
        comodel_name="agora.backend",
        string="Agora Backend",
        required=True,
        ondelete="cascade",
    )
    date_from = fields.Date(
        string="From Business Day",
        required=True,
        default=lambda self: date.today() - timedelta(days=1),
        help="First business day to import (inclusive).",
    )
    date_to = fields.Date(
        string="To Business Day",
        required=True,
        default=lambda self: date.today() - timedelta(days=1),
        help="Last business day to import (inclusive). "
        "Set equal to 'From' to import a single day.",
    )
    advance_watermark = fields.Boolean(
        string="Update 'Last Imported Day'",
        default=False,
        help="If checked, the backend's 'Last Imported Business Day' watermark will "
        "be updated to the last successfully imported day after this import.\n"
        "Useful when the watermark is stuck (e.g. all invoices were skipped "
        "due to missing journal mappings).",
    )
    # Read-only info field
    current_watermark = fields.Date(
        string="Current Last Imported Day",
        related="backend_id.last_imported_business_day",
        readonly=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from > wiz.date_to:
                raise UserError(
                    _(
                        "'From Business Day' must be earlier than or equal"
                        " to 'To Business Day'."
                    )
                )
            if wiz.date_to >= date.today():
                raise UserError(
                    _(
                        "Cannot import today or future dates. "
                        "Agora only closes a business day the following morning."
                    )
                )

    def action_import(self):
        """Execute the manual import for the selected date range."""
        self.ensure_one()
        backend = self.backend_id

        if backend.connection_type != "api":
            raise UserError(
                _(
                    "Manual date import is only available for HTTP API backends. "
                    "For file-based backends, place the files in the export folder "
                    "and use 'Import Invoices'."
                )
            )

        # Build list of days
        pending_days = []
        current = self.date_from
        while current <= self.date_to:
            pending_days.append(current)
            current += timedelta(days=1)

        total_imported = 0
        total_skipped = 0
        total_errors = 0
        days_ok = 0
        last_successful_day = None

        for target_day in pending_days:
            try:
                stats = backend._import_day_from_api(target_day)
            except requests.exceptions.RequestException as e:
                _logger.error(
                    "API error importing business day %s: %s", target_day, str(e)
                )
                total_errors += 1
                break

            total_imported += stats["imported"]
            total_skipped += stats["skipped"]
            total_errors += stats["errors"]

            if stats["errors"] == 0 and (
                stats["imported"] > 0 or stats["invoice_list_count"] == 0
            ):
                last_successful_day = target_day
                days_ok += 1

        # Optionally advance the watermark
        if self.advance_watermark and last_successful_day:
            backend.last_imported_business_day = last_successful_day
            backend.last_import_date = fields.Datetime.now()
            _logger.info(
                "Watermark updated to %s on backend '%s' (manual import wizard)",
                last_successful_day,
                backend.name,
            )

        # Build result message
        if len(pending_days) == 1:
            day_label = pending_days[0].strftime("%d/%m/%Y")
            msg = _(
                "Day %(day)s: %(imported)d invoices imported, %(skipped)d skipped."
            ) % {
                "day": day_label,
                "imported": total_imported,
                "skipped": total_skipped,
            }
        else:
            msg = _(
                "%(days_ok)d of %(total_days)d days processed "
                "(%(day_from)s → %(day_to)s).\n"
                "Total: %(imported)d invoices imported, %(skipped)d skipped."
            ) % {
                "days_ok": days_ok,
                "total_days": len(pending_days),
                "day_from": pending_days[0].strftime("%d/%m/%Y"),
                "day_to": pending_days[-1].strftime("%d/%m/%Y"),
                "imported": total_imported,
                "skipped": total_skipped,
            }

        if total_errors:
            msg += _("\n⚠️ %d errors — check the server logs.") % total_errors
        if total_skipped > 0 and total_imported == 0:
            msg += _(
                "\n⚠️ All invoices were skipped. "
                "Check that Journal mappings are configured in this backend."
            )
        if self.advance_watermark and last_successful_day:
            msg += _("\n✔ Watermark updated to %s.") % last_successful_day.strftime(
                "%d/%m/%Y"
            )

        notification_type = (
            "danger"
            if total_errors and days_ok == 0
            else "warning"
            if total_errors or (total_skipped > 0 and total_imported == 0)
            else "success"
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Agora Manual Import Finished"),
                "message": msg,
                "type": notification_type,
                "sticky": total_errors > 0,
            },
        }
