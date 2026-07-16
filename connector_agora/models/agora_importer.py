# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import date, datetime, timedelta

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AgoraImporter(models.AbstractModel):
    """Mixin that provides HTTP API import logic for AgoraBackend.

    Kept in a separate file to avoid saturating agora_backend.py.
    AgoraBackend inherits this mixin via _inherit.
    """

    _name = "agora.importer"
    _description = "Agora HTTP API Importer"

    def _import_day_from_api(self, target_day):
        """Fetch and import all invoices for a single business day from the API.

        :param target_day: date object for the business day to import.
        :returns: dict with keys ``imported``, ``skipped``, ``errors``,
                  ``invoice_list_count``.
        :raises requests.exceptions.RequestException: on network/API failure.
        :raises UserError: on functional/configuration errors.
        """
        self.ensure_one()
        url = "{}/api/export/".format(self.api_url.rstrip("/"))

        _logger.info("Importing business day %s (backend: %s)", target_day, self.name)
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

        invoice_list = resp.json().get("Invoices", [])
        _logger.info(
            "Agora API returned %d invoices for %s", len(invoice_list), target_day
        )

        if not self.anonymous_partner_id:
            requires_anonymous = 0
            for raw in invoice_list:
                doc_type = (raw.get("DocumentType") or "").lower()
                serie_upper = (raw.get("Serie") or "").upper()
                if "standard" not in doc_type and not serie_upper.startswith(
                    ("FV", "FB")
                ):
                    requires_anonymous += 1
            if requires_anonymous:
                raise UserError(
                    _(
                        "Cannot import business day %(day)s: %(count)d invoices "
                        "require 'Anonymous Customer', but it is not configured "
                        "on backend '%(backend)s'."
                    )
                    % {
                        "day": target_day.strftime("%d/%m/%Y"),
                        "count": requires_anonymous,
                        "backend": self.name,
                    }
                )

        day_imported = 0
        day_skipped = 0
        day_errors = 0

        for raw_invoice in invoice_list:
            invoice_data = self._parse_agora_api_invoice(raw_invoice)
            self.env["agora.account.move"].import_invoice_data(self, invoice_data)
            day_imported += 1

        return {
            "imported": day_imported,
            "skipped": day_skipped,
            "errors": day_errors,
            "invoice_list_count": len(invoice_list),
        }

    def _import_from_api(self):
        """Import invoices from Agora HTTP API for ALL pending business days.

        Agora closes each business day the following morning.
        We loop from (last_imported_business_day + 1) up to yesterday,
        importing every missing day in a single execution.
        """
        self.ensure_one()

        today = date.today()
        yesterday = today - timedelta(days=1)

        # Determine first pending business day
        if self.last_imported_business_day:
            first_pending = self.last_imported_business_day + timedelta(days=1)
        else:
            # First run: start from yesterday
            first_pending = yesterday

        # Build list of all days to import (up to and including yesterday)
        pending_days = []
        current = first_pending
        while current <= yesterday:
            pending_days.append(current)
            current += timedelta(days=1)

        # Nothing pending
        if not pending_days:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Nothing to Import"),
                    "message": _(
                        "All business days are up to date. " "Last imported: %(day)s."
                    )
                    % {
                        "day": (
                            self.last_imported_business_day.strftime("%d/%m/%Y")
                            if self.last_imported_business_day
                            else _("never")
                        )
                    },
                    "type": "info",
                    "sticky": False,
                },
            }

        _logger.info(
            "Backend %s: %d pending business day(s) to import: %s → %s",
            self.name,
            len(pending_days),
            pending_days[0],
            pending_days[-1],
        )

        # Accumulators for the final summary
        total_imported = 0
        total_skipped = 0
        total_errors = 0
        days_ok = 0
        days_with_errors = 0
        last_successful_day = self.last_imported_business_day

        for target_day in pending_days:
            try:
                stats = self._import_day_from_api(target_day)
            except requests.exceptions.RequestException as e:
                _logger.error("API error for business day %s: %s", target_day, str(e))
                raise UserError(
                    _("Agora API error importing business day %(day)s: %(error)s")
                    % {"day": target_day.strftime("%d/%m/%Y"), "error": str(e)}
                ) from e

            total_imported += stats["imported"]
            total_skipped += stats["skipped"]
            total_errors += stats["errors"]

            # Advance watermark only when:
            # - No invoice-level errors AND at least one invoice was imported, OR
            # - The API returned 0 invoices (the day was genuinely empty)
            # If all invoices were skipped (e.g. missing journal mappings),
            # do NOT advance — the day stays pending so it can be retried
            # once the mappings are configured.
            if stats["errors"] == 0 and (
                stats["imported"] > 0 or stats["invoice_list_count"] == 0
            ):
                last_successful_day = target_day
                days_ok += 1
            else:
                days_with_errors += 1

        # Persist watermark and timestamp
        if (
            last_successful_day
            and last_successful_day != self.last_imported_business_day
        ):
            self.last_imported_business_day = last_successful_day
            self.last_import_date = fields.Datetime.now()

        # Build user-facing summary message
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
                "Check that Journal mappings (Journals by venue) are configured "
                "in this backend."
            )

        notification_type = (
            "danger"
            if total_errors and days_ok == 0
            else "warning"
            if total_errors
            else "success"
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Agora Import Finished"),
                "message": msg,
                "type": notification_type,
                "sticky": total_errors > 0,
            },
        }

    def _parse_agora_api_invoice(self, raw):
        """Parse a single invoice dict from the Agora HTTP API JSON response.

        Returns a dict ready for agora.account.move.import_invoice_data().
        Raises UserError on functional/configuration issues to keep imports atomic.
        """
        serie = raw.get("Serie", "")
        number = str(raw.get("Number", ""))
        agora_invoice_id = "{}-{}".format(serie, number)

        doc_type = (raw.get("DocumentType") or "").lower()
        serie_upper = serie.upper()
        # Credit notes: DocumentType has priority; serie prefix is the fallback.
        # rectification_subtype tells which base journal to use:
        # 'normal' (RFV) or 'simplified' (RFS/RFC/RFB).
        if "refund" in doc_type or serie_upper.startswith(("RFC", "RFS", "RFV", "RFB")):
            invoice_type = "rectification"
            move_type = "out_refund"
            rectification_subtype = (
                "normal" if serie_upper.startswith("RFV") else "simplified"
            )
        elif doc_type:
            # DocumentType is present → use it as the authoritative source.
            # "StandardInvoice" → normal | "BasicInvoice" (and any other value) → simplified.
            invoice_type = "normal" if doc_type == "standardinvoice" else "simplified"
            move_type = "out_invoice"
            rectification_subtype = None
        else:
            # No DocumentType → fall back to serie prefix.
            # FV (FV803...) and FB (FB423...) = StandardInvoice → normal.
            # FS (FS423...) and FC (FC423...) = BasicInvoice → simplified.
            invoice_type = (
                "normal" if serie_upper.startswith(("FV", "FB")) else "simplified"
            )
            move_type = "out_invoice"
            rectification_subtype = None

        workplace = raw.get("Workplace") or {}
        workplace_id = int(workplace.get("Id", 0))
        workplace_name = workplace.get("Name", "")

        journal_id = self._resolve_journal(
            workplace_id, invoice_type, rectification_subtype
        )
        if not journal_id:
            raise UserError(
                _(
                    "Missing journal mapping for workplace %(name)s (%(id)s), "
                    "invoice type %(invoice_type)s. Invoice: %(invoice)s"
                )
                % {
                    "name": workplace_name or "-",
                    "id": workplace_id,
                    "invoice_type": invoice_type,
                    "invoice": agora_invoice_id,
                }
            )

        # Rule: only standardinvoice includes real customer data.
        # basicinvoice always uses the anonymous partner, even if the JSON has a Customer field.
        if "standard" in doc_type:
            partner_id = self._resolve_invoice_partner(raw)
        else:
            partner_id = (
                self.anonymous_partner_id.id if self.anonymous_partner_id else False
            )

        # Resolve income account:
        # 1. Use the fixed account configured on the backend (if any)
        # 2. Otherwise use the default account of the mapped journal
        # 3. Last resort: first income account found in the company
        journal = self.env["account.journal"].browse(journal_id)
        journal_company_id = journal.company_id.id
        if self.income_account_id:
            account_id = self.income_account_id.id
        else:
            account_id = (
                journal.default_account_id.id
                if journal.default_account_id
                else self._resolve_income_account()
            )

        # HU-04: import Agora unit price as-is (tax-included) from UnitPrice/PrecioUnit.
        lines = []
        for item in raw.get("InvoiceItems", []):
            # Discount applied at InvoiceItem level (not at individual line level).
            # DiscountRate is a fraction: 1.0 = 100%, 0.5 = 50%, etc.
            item_discount_rate = float(
                (item.get("Discounts") or {}).get("DiscountRate", 0)
            )
            item_lines = item.get("Lines", [])

            for line in item_lines:
                vat_rate = float(line.get("VatRate", 0))
                qty = float(line.get("Quantity", 1))
                if doc_type == "basicrefund":
                    qty = abs(qty)
                raw_unit = (
                    line.get("UnitPrice")
                    or line.get("PrecioUnit")
                    or line.get("unit_price")
                    or 0
                )
                # Keep discount handling at InvoiceItem level and persist the
                # resulting tax-included unit price in Odoo.
                price_unit = float(raw_unit) * (1 - item_discount_rate)

                tax_ids = self._resolve_tax_ids(
                    round(vat_rate * 100, 2), journal_company_id
                )
                lines.append(
                    {
                        "name": line.get("ProductName", _("Product")),
                        "quantity": qty,
                        "price_unit": price_unit,
                        "tax_ids": tax_ids,
                        "account_id": account_id,
                    }
                )

        if not lines:
            raise UserError(
                _("Invoice %(invoice)s has no lines and cannot be imported.")
                % {"invoice": agora_invoice_id}
            )

        invoice_date = (raw.get("Date") or "")[:10]
        business_day = (raw.get("BusinessDay") or invoice_date)[:10]

        # Reference format: "FC4232026-03054 - Cierre 423: 18.03.26"
        # For credit notes: "RFS423-00001 Rectifica: FC423-03054 - Cierre 423: 18.03.26"
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
        # For credit notes, add a reference to the original invoice.
        if invoice_type == "rectification":
            orig_serie = (
                raw.get("OriginalSerie") or raw.get("OriginalInvoiceSerie") or ""
            ).strip()
            orig_number = str(
                raw.get("OriginalNumber") or raw.get("OriginalInvoiceNumber") or ""
            ).strip()
            if orig_serie or orig_number:
                ref = "{} Rectifica: {}-{}".format(
                    ref, orig_serie, orig_number.zfill(5)
                )

        return {
            "agora_invoice_id": agora_invoice_id,
            "agora_document_type": invoice_type,
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

    def _resolve_journal(self, workplace_id, invoice_type, rectification_subtype=None):
        """Find the Odoo journal from the agora.journal.mapping table.

        Credit notes do not need their own mapping: they use the same journal
        as their base type — RFV → 'normal' journal, RFS/RFC/RFB → 'simplified' journal.
        """
        mapping = self.agora_journal_ids.filtered(
            lambda m: m.workplace_id == workplace_id and m.invoice_type == invoice_type
        )
        if mapping:
            return mapping[:1].journal_id.id
        # Credit notes: look for the journal of the matching base type.
        if invoice_type == "rectification":
            base_type = rectification_subtype or "simplified"
            fallback = self.agora_journal_ids.filtered(
                lambda m: m.workplace_id == workplace_id and m.invoice_type == base_type
            )
            return fallback[:1].journal_id.id if fallback else False
        return False

    def _resolve_invoice_partner(self, raw):
        """Find or create partner from the Customer field of the Agora invoice.

        The Customer object is at the invoice root level (not inside InvoiceItems).
        Logic:
          1. If no Customer key → anonymous partner.
          2. Search by VAT (Cif), trying both with and without 'ES' prefix.
          3. If not found → create the partner with available data.
          4. Fallback → anonymous partner.
        """
        customer = raw.get("Customer")
        if not customer or not customer.get("Id"):
            return self.anonymous_partner_id.id if self.anonymous_partner_id else False

        cif = (customer.get("Cif") or "").strip()
        name = (customer.get("FiscalName") or "").strip()
        if not name:
            name = "Agora Customer {}".format(customer.get("Id", "unknown"))

        # Search by VAT: try exact CIF and with ES prefix
        if cif:
            partner = self.env["res.partner"].search(
                [("vat", "in", [cif, "ES{}".format(cif)])], limit=1
            )
            if partner:
                return partner.id

        # Search by name if no VAT match
        if name:
            partner = self.env["res.partner"].search([("name", "=", name)], limit=1)
            if partner:
                return partner.id

        # Create the partner with data from Agora
        country_code = (customer.get("CountryCode") or "ES").strip()
        country = self.env["res.country"].search([("code", "=", country_code)], limit=1)
        vals = {
            "name": name or "Agora Customer {}".format(customer.get("Id")),
            "is_company": True,
            "customer_rank": 1,
            "street": customer.get("Street") or False,
            "city": customer.get("City") or False,
            "zip": customer.get("ZipCode") or False,
            "country_id": country.id if country else False,
        }
        if cif:
            vals["vat"] = cif if cif.startswith("ES") else "ES{}".format(cif)

        try:
            partner = self.env["res.partner"].create(vals)
            _logger.info(
                "Created new partner '%s' (VAT: %s) from Agora Customer id=%s",
                vals["name"],
                vals.get("vat"),
                customer.get("Id"),
            )
            return partner.id
        except Exception as e:
            _logger.warning(
                "Could not create partner for Agora Customer id=%s name='%s':"
                " %s — using anonymous",
                customer.get("Id"),
                name,
                str(e),
            )
            return self.anonymous_partner_id.id if self.anonymous_partner_id else False
