# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import date, datetime, timedelta

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AgoraImporter(models.AbstractModel):
    """Mixin that provides HTTP API import logic for AgoraBackend.

    Kept in a separate file to avoid saturating agora_backend.py.
    AgoraBackend inherits this mixin via _inherit.
    """

    _name = "agora.importer"
    _description = "Agora HTTP API Importer"

    def _import_from_api(self):
        """Import invoices from Agora HTTP API for the next pending business day.

        Agora closes each business day the following morning.
        We import day by day starting from (last_imported_business_day + 1)
        up to yesterday (today's close is not done yet).
        """
        self.ensure_one()

        # Determine which business day to fetch
        if self.last_imported_business_day:
            target_day = self.last_imported_business_day + timedelta(days=1)
        else:
            # First run: start from yesterday
            target_day = date.today() - timedelta(days=1)

        today = date.today()
        if target_day >= today:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Nothing to Import"),
                    "message": _(
                        "No closed business days pending import. "
                        "Agora closes each day the following morning."
                    ),
                    "type": "info",
                    "sticky": False,
                },
            }

        _logger.info(
            "Importing Agora invoices for business day %s (backend: %s)",
            target_day,
            self.name,
        )

        # Call the API
        url = "{}/api/export/".format(self.api_url.rstrip("/"))
        try:
            resp = requests.get(
                url,
                headers={
                    "Api-Token": self.api_token,
                    "Accept": "application/json",
                },
                params={
                    "filter": "Invoices",
                    "business-day": target_day.strftime("%Y-%m-%d"),
                },
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ValidationError(_("Error calling Agora API: %s") % str(e)) from e

        data = resp.json()
        invoice_list = data.get("Invoices", [])
        _logger.info(
            "Agora API returned %d invoices for %s", len(invoice_list), target_day
        )

        imported = 0
        skipped = 0
        errors = 0

        for raw_invoice in invoice_list:
            try:
                invoice_data = self._parse_agora_api_invoice(raw_invoice)
                if not invoice_data:
                    skipped += 1
                    continue
                self.env["agora.account.move"].import_invoice_data(self, invoice_data)
                imported += 1
            except Exception as e:
                serie = raw_invoice.get("Serie", "?")
                number = raw_invoice.get("Number", "?")
                _logger.error(
                    "Error importing Agora invoice %s-%s: %s", serie, number, str(e)
                )
                errors += 1

        # Advance the last imported business day only if no critical errors
        if errors == 0 or imported > 0:
            self.last_imported_business_day = target_day
            self.last_import_date = fields.Datetime.now()

        msg = _("Business day %(day)s: %(imported)d imported, %(skipped)d skipped") % {
            "day": target_day.strftime("%d/%m/%Y"),
            "imported": imported,
            "skipped": skipped,
        }
        if errors:
            msg += _(", %d errors (check logs)") % errors

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Agora Import Finished"),
                "message": msg,
                "type": "success" if not errors else "warning",
                "sticky": False,
            },
        }

    def _parse_agora_api_invoice(self, raw):
        """Parse a single invoice dict from the Agora HTTP API JSON response.

        Returns a dict ready for agora.account.move.import_invoice_data(),
        or None if the invoice should be skipped (no journal mapping, no lines).
        """
        serie = raw.get("Serie", "")
        number = str(raw.get("Number", ""))
        agora_invoice_id = "{}-{}".format(serie, number)

        doc_type = (raw.get("DocumentType") or "").lower()
        serie_upper = serie.upper()
        if "refund" in doc_type or serie_upper.startswith(("RFC", "RFS", "RFV", "RFB")):
            invoice_type = "rectification"
            move_type = "out_refund"
        elif "standard" in doc_type or serie_upper.startswith(("FV", "FB")):
            invoice_type = "normal"
            move_type = "out_invoice"
        else:
            invoice_type = "simplified"
            move_type = "out_invoice"

        workplace = raw.get("Workplace") or {}
        workplace_id = int(workplace.get("Id", 0))
        workplace_name = workplace.get("Name", "")

        journal_id = self._resolve_journal(workplace_id, invoice_type)
        if not journal_id:
            _logger.warning(
                "No journal mapping for workplace %s (%s) type %s — skipping %s",
                workplace_name,
                workplace_id,
                invoice_type,
                agora_invoice_id,
            )
            return None

        if invoice_type == "simplified":
            partner_id = (
                self.anonymous_partner_id.id if self.anonymous_partner_id else False
            )
        else:
            partner_id = self._resolve_invoice_partner(raw)

        account_id = (
            self.income_account_id.id
            if self.income_account_id
            else self._resolve_income_account()
        )

        # UnitPrice from Agora includes VAT → convert to net price for Odoo
        lines = []
        for item in raw.get("InvoiceItems", []):
            for line in item.get("Lines", []):
                vat_rate = float(line.get("VatRate", 0))
                unit_price_with_vat = float(line.get("UnitPrice", 0))
                price_unit = (
                    round(unit_price_with_vat / (1 + vat_rate), 6)
                    if vat_rate
                    else unit_price_with_vat
                )
                tax_ids = self._resolve_tax_ids(round(vat_rate * 100, 2))
                lines.append(
                    {
                        "name": line.get("ProductName", _("Product")),
                        "quantity": float(line.get("Quantity", 1)),
                        "price_unit": price_unit,
                        "tax_ids": tax_ids,
                        "account_id": account_id,
                    }
                )

        if not lines:
            _logger.warning("Invoice %s has no lines, skipping", agora_invoice_id)
            return None

        invoice_date = (raw.get("Date") or "")[:10]
        business_day = (raw.get("BusinessDay") or invoice_date)[:10]

        # Reference format: "FC4232026-03054 - Cierre 423: 18.03.26"
        digits = "".join(filter(str.isdigit, serie))
        cierre_num = digits[:-4] if len(digits) >= 4 else digits
        day_str = ""
        if business_day:
            try:
                day_str = datetime.strptime(business_day, "%Y-%m-%d").strftime(
                    "%d.%m.%y"
                )
            except ValueError:
                day_str = business_day
        ref = "{}-{} - Cierre {}: {}".format(
            serie, number.zfill(5), cierre_num, day_str
        )

        return {
            "agora_invoice_id": agora_invoice_id,
            "agora_document_type": "invoice",
            "agora_workplace_id": workplace_id,
            "agora_workplace_name": workplace_name,
            "agora_pos_id": int((raw.get("Pos") or {}).get("Id", 0)),
            "agora_business_day": business_day,
            "agora_series": serie,
            "agora_number": number,
            "agora_customer_id": "",
            "invoice_date": invoice_date,
            "partner_id": partner_id,
            "journal_id": journal_id,
            "move_type": move_type,
            "lines": lines,
            "ref": ref,
            "raw_data": json.dumps(raw),
        }

    def _resolve_journal(self, workplace_id, invoice_type):
        """Find the Odoo journal from the agora.journal.mapping table."""
        mapping = self.agora_journal_ids.filtered(
            lambda m: m.workplace_id == workplace_id and m.invoice_type == invoice_type
        )
        return mapping[:1].journal_id.id if mapping else False

    def _resolve_invoice_partner(self, raw):
        """Find or fall back to anonymous partner for normal invoices.

        Phase 1: match by CIF/NIF if present.
        Phase 2 (future): full customer create logic.
        """
        for item in raw.get("InvoiceItems", []):
            customer = item.get("Customer")
            if customer and customer.get("Id"):
                cif = customer.get("Cif") or customer.get("FiscalId") or ""
                if cif:
                    partner = self.env["res.partner"].search(
                        [("vat", "in", [cif, "ES{}".format(cif)])], limit=1
                    )
                    if partner:
                        return partner.id
        return self.anonymous_partner_id.id if self.anonymous_partner_id else False
