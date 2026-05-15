# © 2026 Comunitea
# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# © 2026 Jose Luis Algara <osotranquilo@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
# Based on connector_docuware structure

import json
import logging
import os
import xml.etree.ElementTree as ET

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AgoraBackend(models.Model):
    """Backend configuration for Agora POS integration"""

    _name = "agora.backend"
    _inherit = ["mail.thread", "connector.backend", "agora.importer"]
    _description = "Agora POS Backend"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    # Connection settings
    connection_type = fields.Selection(
        [
            ("file", "File-based Export (Recommended)"),
            ("api", "HTTP API"),
        ],
        required=True,
        default="api",
        tracking=True,
        help="File-based: Monitor export folder for XML/JSON files.\n"
        "HTTP API: Poll Agora HTTP API for data.",
    )

    # File-based settings
    export_folder_path = fields.Char(
        help="Local path where Agora exports XML/JSON files (ais.exe output folder)",
        tracking=True,
    )
    file_format = fields.Selection(
        [("xml", "XML"), ("json", "JSON")],
        default="xml",
        help="Format of exported files from Agora",
    )
    auto_process_files = fields.Boolean(
        default=True,
        help="Automatically import new files detected in export folder",
    )

    # HTTP API settings
    api_url = fields.Char(
        help="Agora HTTP API base URL (e.g., https://acms.gestionalda.com)",
        tracking=True,
    )
    api_token = fields.Char(
        help="Authentication token for Agora HTTP API",
        tracking=True,
    )

    # Invoice import configuration
    anonymous_partner_id = fields.Many2one(
        "res.partner",
        string="Anonymous Customer",
        help="Partner used for simplified invoices (Facturas Simplificadas)",
        tracking=True,
    )
    income_account_id = fields.Many2one(
        "account.account",
        string="Income Account",
        help="Fixed income account for all invoice lines (e.g. 70500000021 Restauración)",
        tracking=True,
    )
    last_imported_business_day = fields.Date(
        readonly=True,
        tracking=True,
        help="Last Agora business day successfully imported. "
        "Next import will fetch the following day.",
    )
    agora_journal_ids = fields.One2many(
        "agora.journal.mapping",
        "backend_id",
        string="Journal Mappings",
        help="Map each Agora workplace + invoice type to the correct Odoo journal",
    )

    # Import configuration
    import_invoices = fields.Boolean(
        default=True,
        help="Import sales invoices from Agora",
    )
    import_pos_closeouts = fields.Boolean(
        default=False,
        help="Import POS cash register closeouts (cierres de caja)",
    )
    import_system_closeouts = fields.Boolean(
        default=False,
        help="Import system closeouts (cierres de sistema)",
    )

    # Mapping tables
    agora_property_ids = fields.One2many(
        "agora.property",
        "backend_id",
        help="Map Agora workplaces to PMS properties",
    )
    agora_payment_mode_ids = fields.One2many(
        "agora.payment.mode",
        "backend_id",
        help="Map Agora payment methods to Odoo payment modes",
    )

    # Execution settings
    execute_user_id = fields.Many2one(
        "res.users",
        help="User for executing background jobs",
        default=lambda self: self.env.user,
    )

    # Statistics
    last_import_date = fields.Datetime(
        readonly=True,
        tracking=True,
    )
    invoice_count = fields.Integer(
        compute="_compute_invoice_count",
    )

    def _compute_invoice_count(self):
        """Compute number of invoices imported from this backend"""
        for backend in self:
            backend.invoice_count = self.env["agora.account.move"].search_count(
                [("backend_id", "=", backend.id)]
            )

    @api.constrains("connection_type", "export_folder_path", "api_url")
    def _check_connection_settings(self):
        """Validate connection settings based on connection type"""
        for backend in self:
            if backend.connection_type == "file" and not backend.export_folder_path:
                raise ValidationError(
                    _("Export folder path is required for file-based connection")
                )
            if backend.connection_type == "api" and not backend.api_url:
                raise ValidationError(_("API URL is required for HTTP API connection"))

    @api.constrains("export_folder_path")
    def _check_export_folder_exists(self):
        """Validate that export folder exists and is accessible"""
        for backend in self:
            if backend.export_folder_path:
                if not os.path.exists(backend.export_folder_path):
                    raise ValidationError(
                        _("Export folder does not exist: %s")
                        % backend.export_folder_path
                    )
                if not os.path.isdir(backend.export_folder_path):
                    raise ValidationError(
                        _("Export folder path is not a directory: %s")
                        % backend.export_folder_path
                    )

    def action_test_connection(self):
        """Test connection to Agora (file folder or HTTP API)"""
        self.ensure_one()
        if self.connection_type == "file":
            return self._test_file_connection()
        else:
            return self._test_api_connection()

    def _test_file_connection(self):
        """Test file-based connection"""
        self.ensure_one()
        try:
            files = os.listdir(self.export_folder_path)
            xml_files = [f for f in files if f.endswith((".xml", ".json"))]
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Connection Test Successful"),
                    "message": _("Found %d export files in folder") % len(xml_files),
                    "type": "success",
                    "sticky": False,
                },
            }
        except Exception as e:
            raise ValidationError(
                _("Failed to access export folder: %s") % str(e)
            ) from e

    def _test_api_connection(self):
        """Test HTTP API connection by calling /api/export-master/?filter=Series"""
        self.ensure_one()
        try:
            url = "{}/api/export-master/".format(self.api_url.rstrip("/"))
            resp = requests.get(
                url,
                headers={
                    "Api-Token": self.api_token,
                    "Accept": "application/json",
                },
                params={"filter": "Series"},
                timeout=15,
            )
            resp.raise_for_status()
            api_version = resp.headers.get("Api-Version", "unknown")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Connection Test Successful"),
                    "message": _("Connected to Agora API version %s") % api_version,
                    "type": "success",
                    "sticky": False,
                },
            }
        except requests.exceptions.ConnectionError as e:
            raise ValidationError(
                _("Cannot connect to Agora API at %(url)s: %(error)s")
                % {"url": self.api_url, "error": str(e)}
            ) from e
        except requests.exceptions.Timeout as e:
            raise ValidationError(
                _("Connection to Agora API timed out (15s): %s") % self.api_url
            ) from e
        except requests.exceptions.HTTPError as e:
            raise ValidationError(
                _("Agora API returned error %(status)s: %(error)s")
                % {"status": e.response.status_code, "error": str(e)}
            ) from e

    def action_import_invoices(self):
        """Manual trigger to import invoices from Agora"""
        self.ensure_one()
        if self.connection_type == "file":
            return self._import_from_files()
        else:
            return self._import_from_api()

    def _import_from_files(self):
        """Import invoices from XML/JSON files in the export folder"""
        self.ensure_one()
        folder = self.export_folder_path
        _logger.info("Importing invoices from files in %s", folder)
        imported = 0
        errors = 0
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith((".xml", ".json")):
                continue
            filepath = os.path.join(folder, filename)
            try:
                invoices = self._parse_export_file(filepath)
                for invoice_data in invoices:
                    invoice_data["source_file"] = filename
                    self.env["agora.account.move"].import_invoice_data(
                        self, invoice_data
                    )
                    imported += 1
            except Exception as e:
                _logger.error("Error processing file %s: %s", filename, str(e))
                errors += 1
                continue

        self.last_import_date = fields.Datetime.now()
        msg = _("Imported %d invoices from files") % imported
        if errors:
            msg += _(", %d files with errors (check logs)") % errors
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Import Finished"),
                "message": msg,
                "type": "success" if not errors else "warning",
                "sticky": False,
            },
        }

    def _parse_export_file(self, filepath):
        """Parse an XML or JSON export file and return a list of invoice dicts.

        Agora XML example structure (ais.exe export):
          <Invoices>
            <Invoice Id="..." Series="..." Number="..." Date="..." ...>
              <Customer Id="..." />
              <Lines>
                <Line Description="..." Quantity="..." UnitPrice="..." TaxRate="..." />
              </Lines>
            </Invoice>
          </Invoices>
        """
        if filepath.endswith(".json"):
            return self._parse_json_file(filepath)
        return self._parse_xml_file(filepath)

    def _parse_xml_file(self, filepath):
        """Parse Agora XML export file"""
        invoices = []
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except ET.ParseError as e:
            raise ValidationError(
                _("Invalid XML file %(file)s: %(error)s")
                % {"file": filepath, "error": str(e)}
            ) from e

        # Support both <Invoices><Invoice> and root being <Invoice>
        invoice_nodes = root.findall("Invoice") or (
            [root] if root.tag == "Invoice" else []
        )
        for node in invoice_nodes:
            invoice_data = self._xml_node_to_invoice(node, filepath)
            if invoice_data:
                invoices.append(invoice_data)
        return invoices

    def _xml_node_to_invoice(self, node, filepath):
        """Convert an <Invoice> XML node to an invoice dict"""
        agora_id = node.get("Id") or node.get("id")
        if not agora_id:
            _logger.warning("Invoice node without Id in %s, skipping", filepath)
            return None

        raw_data = ET.tostring(node, encoding="unicode")

        # Resolve taxes from TaxRate attribute on each line
        lines = []
        for line_node in node.findall(".//Line"):
            tax_rate = float(line_node.get("TaxRate", 0))
            tax_ids = self._resolve_tax_ids(tax_rate)
            account_id = self._resolve_income_account()
            lines.append(
                {
                    "name": line_node.get("Description", _("Product")),
                    "quantity": float(line_node.get("Quantity", 1)),
                    "price_unit": float(line_node.get("UnitPrice", 0)),
                    "tax_ids": tax_ids,
                    "account_id": account_id,
                }
            )

        customer_node = node.find("Customer")
        customer_id = customer_node.get("Id", "") if customer_node is not None else ""

        workplace_node = node.find("Workplace") or node.find("Local")
        workplace_id = 0
        workplace_name = node.get("WorkplaceName", "")
        if workplace_node is not None:
            workplace_id = int(workplace_node.get("Id", 0))
            workplace_name = workplace_node.get("Name", workplace_name)

        invoice_date = node.get("Date", "") or node.get("InvoiceDate", "")
        business_day = node.get("BusinessDay", "") or invoice_date

        return {
            "agora_invoice_id": agora_id,
            "agora_document_type": self._resolve_document_type(
                node.get("Type", "invoice")
            ),
            "agora_workplace_id": workplace_id,
            "agora_workplace_name": workplace_name,
            "agora_pos_id": int(node.get("PosId", 0)),
            "agora_business_day": business_day[:10] if business_day else False,
            "agora_series": node.get("Series", ""),
            "agora_number": node.get("Number", ""),
            "agora_customer_id": customer_id,
            "invoice_date": invoice_date[:10] if invoice_date else False,
            "lines": lines,
            "raw_data": raw_data,
        }

    def _parse_json_file(self, filepath):
        """Parse Agora JSON export file"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Accept both a list at root or {"invoices": [...]}
        if isinstance(data, list):
            invoice_list = data
        elif isinstance(data, dict):
            invoice_list = data.get("invoices") or data.get("Invoices") or [data]
        else:
            return []

        invoices = []
        for item in invoice_list:
            agora_id = str(item.get("Id") or item.get("id", ""))
            if not agora_id:
                continue
            lines = []
            for line in item.get("Lines") or item.get("lines") or []:
                tax_rate = float(line.get("TaxRate") or line.get("tax_rate", 0))
                tax_ids = self._resolve_tax_ids(tax_rate)
                account_id = self._resolve_income_account()
                lines.append(
                    {
                        "name": line.get("Description")
                        or line.get("name", _("Product")),
                        "quantity": float(
                            line.get("Quantity") or line.get("quantity", 1)
                        ),
                        "price_unit": float(
                            line.get("UnitPrice") or line.get("unit_price", 0)
                        ),
                        "tax_ids": tax_ids,
                        "account_id": account_id,
                    }
                )
            invoice_date = (
                item.get("Date")
                or item.get("InvoiceDate")
                or item.get("invoice_date", "")
            )
            business_day = (
                item.get("BusinessDay") or item.get("business_day") or invoice_date
            )
            invoices.append(
                {
                    "agora_invoice_id": agora_id,
                    "agora_document_type": self._resolve_document_type(
                        item.get("Type") or item.get("type", "invoice")
                    ),
                    "agora_workplace_id": int(
                        item.get("WorkplaceId") or item.get("workplace_id", 0)
                    ),
                    "agora_workplace_name": item.get("WorkplaceName")
                    or item.get("workplace_name", ""),
                    "agora_pos_id": int(item.get("PosId") or item.get("pos_id", 0)),
                    "agora_business_day": business_day[:10] if business_day else False,
                    "agora_series": item.get("Series") or item.get("series", ""),
                    "agora_number": item.get("Number") or item.get("number", ""),
                    "agora_customer_id": str(
                        item.get("CustomerId") or item.get("customer_id", "")
                    ),
                    "invoice_date": invoice_date[:10] if invoice_date else False,
                    "lines": lines,
                    "raw_data": json.dumps(item),
                }
            )
        return invoices

    @staticmethod
    def _resolve_document_type(raw_type):
        """Normalise Agora document type to selection value"""
        mapping = {
            "invoice": "invoice",
            "factura": "invoice",
            "ticket": "ticket",
            "roomcharge": "room_charge",
            "room_charge": "room_charge",
        }
        return mapping.get(str(raw_type).lower(), "invoice")

    def _resolve_tax_ids(self, tax_rate, company_id=None):
        """Find the account.tax ID matching the given rate (sale type).

        :param tax_rate: numeric tax rate (e.g. 10.0 for 10%)
        :param company_id: company to search in; defaults to self.env.company.id
        """
        if not tax_rate:
            return []
        company_id = company_id or self.env.company.id
        tax = self.env["account.tax"].search(
            [
                ("amount", "=", tax_rate),
                ("type_tax_use", "=", "sale"),
                ("company_id", "=", company_id),
            ],
            limit=1,
        )
        if not tax:
            company_name = self.env["res.company"].browse(company_id).name
            _logger.warning(
                "No sale tax with rate %s%% found for company '%s'. "
                "Install the Spanish fiscal localization for this company "
                "or create the missing tax manually.",
                tax_rate,
                company_name,
            )
        return [tax.id] if tax else []

    def _resolve_income_account(self):
        """Return a default income account for invoice lines"""
        account = self.env["account.account"].search(
            [
                ("account_type", "in", ["income", "income_other"]),
                ("company_id", "=", self.env.company.id),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        return account.id if account else False

    def action_view_invoices(self):
        """Open the list of account.move invoices imported from this backend"""
        self.ensure_one()
        agora_moves = self.env["agora.account.move"].search(
            [("backend_id", "=", self.id)]
        )
        odoo_ids = agora_moves.mapped("odoo_id").ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Agora Invoices"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", odoo_ids)],
            "context": {
                "default_move_type": "out_invoice",
                "search_default_sale_journal": 1,
            },
        }

    @api.model
    def cron_import_agora_invoices(self):
        """Cron job to automatically import invoices from all active backends"""
        backends = self.search(
            [("active", "=", True), ("auto_process_files", "=", True)]
        )
        for backend in backends:
            try:
                backend.action_import_invoices()
            except Exception as e:
                _logger.error(
                    "Error importing invoices from backend %s: %s",
                    backend.name,
                    str(e),
                )

    def map_property(self, workplace_name):
        """Map Agora workplace to PMS property"""
        self.ensure_one()
        mapping = self.agora_property_ids.filtered(
            lambda r: r.workplace_name == workplace_name
        )
        if not mapping:
            raise ValidationError(
                _("Property mapping not found for workplace: %s") % workplace_name
            )
        return mapping.property_id

    def map_payment_mode(self, payment_method_name):
        """Map Agora payment method to Odoo payment mode"""
        self.ensure_one()
        mapping = self.agora_payment_mode_ids.filtered(
            lambda r: r.agora_name == payment_method_name
        )
        if not mapping:
            _logger.warning(
                "Payment mode mapping not found for: %s (backend: %s)",
                payment_method_name,
                self.name,
            )
            return False
        return mapping.payment_mode_id


class AgoraJournalMapping(models.Model):
    """Map Agora workplace + invoice type to an Odoo journal"""

    _name = "agora.journal.mapping"
    _description = "Agora Journal Mapping"

    backend_id = fields.Many2one("agora.backend", required=True, ondelete="cascade")
    workplace_id = fields.Integer(
        required=True,
        help="Numeric ID of the Agora workplace (e.g. 2 for RESTAURANTE PUNTA DEL ESTE)",
    )
    workplace_name = fields.Char(
        help="Optional label for reference",
    )
    invoice_type = fields.Selection(
        [
            ("simplified", "Simplified Invoice"),
            ("normal", "Normal Invoice"),
        ],
        required=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        string="Odoo Journal",
        domain=[("type", "=", "sale")],
    )

    _sql_constraints = [
        (
            "unique_workplace_type_backend",
            "unique(backend_id, workplace_id, invoice_type)",
            "Only one journal mapping per workplace + invoice type per backend",
        )
    ]


class AgoraProperty(models.Model):
    """Mapping between Agora workplaces and PMS properties"""

    _name = "agora.property"
    _description = "Agora Property Mapping"

    workplace_name = fields.Char(string="Agora Workplace Name", required=True)
    workplace_id = fields.Integer(string="Agora Workplace ID")
    property_id = fields.Many2one("pms.property", string="PMS Property")
    backend_id = fields.Many2one("agora.backend", string="Backend", required=True)

    _sql_constraints = [
        (
            "unique_workplace_backend",
            "unique(workplace_name, backend_id)",
            "Workplace name must be unique per backend",
        )
    ]


class AgoraPaymentMode(models.Model):
    """Mapping between Agora payment methods and Odoo payment modes"""

    _name = "agora.payment.mode"
    _description = "Agora Payment Mode Mapping"

    agora_name = fields.Char(string="Agora Payment Method Name", required=True)
    agora_id = fields.Integer(string="Agora Payment Method ID")
    payment_mode_id = fields.Many2one(
        "account.payment.mode",
        string="Odoo Payment Mode",
        required=True,
        company_dependent=True,
    )
    backend_id = fields.Many2one("agora.backend", string="Backend", required=True)

    _sql_constraints = [
        (
            "unique_payment_backend",
            "unique(agora_name, backend_id)",
            "Payment method name must be unique per backend",
        )
    ]
