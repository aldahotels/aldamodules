# © 2026 Comunitea
# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# © 2026 Jose Luis Algara <osotranquilo@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
# Based on connector_docuware structure

import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Extend account.move to add Agora binding"""

    _inherit = "account.move"

    agora_bind_ids = fields.One2many(
        comodel_name="agora.account.move",
        inverse_name="odoo_id",
        string="Agora Bindings",
    )

    agora_invoice_ref = fields.Char(
        string="Agora Invoice",
        compute="_compute_agora_invoice_ref",
        store=True,
        help="Invoice number from Agora POS (series + number)",
    )

    agora_origin = fields.Char(
        compute="_compute_agora_invoice_ref",
        store=True,
        help="Workplace / POS origin from Agora",
    )

    @api.depends(
        "agora_bind_ids",
        "agora_bind_ids.agora_series",
        "agora_bind_ids.agora_number",
        "agora_bind_ids.agora_workplace_name",
    )
    def _compute_agora_invoice_ref(self):
        for move in self:
            binding = move.agora_bind_ids[:1]
            if binding:
                series = binding.agora_series or ""
                number = binding.agora_number or ""
                move.agora_invoice_ref = (
                    "{} {}".format(series, number).strip() or binding.agora_invoice_id
                )
                move.agora_origin = binding.agora_workplace_name or ""
            else:
                move.agora_invoice_ref = False
                move.agora_origin = False


class AgoraAccountMove(models.Model):
    """Binding between Odoo invoices and Agora invoices"""

    _name = "agora.account.move"
    _inherit = "external.binding"
    _inherits = {"account.move": "odoo_id"}
    _description = "Agora Invoice Binding"

    odoo_id = fields.Many2one(
        comodel_name="account.move",
        required=True,
        ondelete="cascade",
    )
    backend_id = fields.Many2one(
        comodel_name="agora.backend",
        required=True,
        ondelete="restrict",
    )

    # Agora fields
    agora_invoice_id = fields.Char(
        string="Agora Invoice ID",
        readonly=True,
        help="Unique invoice identifier from Agora (Id attribute)",
    )
    agora_document_type = fields.Selection(
        [
            ("invoice", "Invoice"),
            ("ticket", "Ticket"),
            ("room_charge", "Room Charge"),
        ],
        readonly=True,
    )
    agora_workplace_id = fields.Integer(
        readonly=True,
        help="ID of the Agora workplace (Local) where invoice was created",
    )
    agora_workplace_name = fields.Char(
        readonly=True,
    )
    agora_pos_id = fields.Integer(
        readonly=True,
        help="Point of sale ID where invoice was created",
    )
    agora_business_day = fields.Date(
        readonly=True,
        help="Business day when invoice was created in Agora",
    )
    agora_series = fields.Char(
        readonly=True,
        help="Invoice series from Agora",
    )
    agora_number = fields.Char(
        readonly=True,
        help="Invoice number from Agora",
    )
    agora_customer_id = fields.Char(
        readonly=True,
    )

    import_date = fields.Datetime(
        readonly=True,
        help="Date when this invoice was imported from Agora",
    )
    source_file = fields.Char(
        readonly=True,
        help="XML/JSON file from which this invoice was imported",
    )
    raw_data = fields.Text(
        readonly=True,
        help="Original XML/JSON data from Agora (for debugging)",
    )

    _sql_constraints = [
        (
            "agora_invoice_unique",
            "unique(backend_id, agora_invoice_id)",
            "Agora invoice ID must be unique per backend",
        ),
    ]

    def import_invoice_data(self, backend, invoice_data):
        """Import invoice data from Agora XML/JSON and create/update account.move.

        :param backend: agora.backend record
        :param invoice_data: dict with parsed invoice fields:
            {
                'agora_invoice_id': str,        # Unique Agora ID
                'agora_document_type': str,     # 'invoice'|'ticket'|'room_charge'
                'agora_workplace_id': int,
                'agora_workplace_name': str,
                'agora_pos_id': int,
                'agora_business_day': date str  # 'YYYY-MM-DD'
                'agora_series': str,
                'agora_number': str,
                'agora_customer_id': str,
                'invoice_date': str,            # 'YYYY-MM-DD'
                'partner_id': int or False,
                'journal_id': int,              # Sales journal ID
                'currency_id': int or False,
                'lines': [
                    {
                        'name': str,
                        'quantity': float,
                        'price_unit': float,
                        'tax_ids': [int, ...],  # account.tax IDs
                        'account_id': int,
                    },
                    ...
                ],
                'source_file': str or False,
                'raw_data': str or False,
            }
        :return: agora.account.move record
        """
        AgoraMove = self.env["agora.account.move"]

        # Check for duplicates
        existing = AgoraMove.search(
            [
                ("backend_id", "=", backend.id),
                ("agora_invoice_id", "=", invoice_data["agora_invoice_id"]),
            ],
            limit=1,
        )
        if existing:
            _logger.debug(
                "Invoice %s already imported, skipping",
                invoice_data["agora_invoice_id"],
            )
            return existing

        # Resolve partner
        partner_id = invoice_data.get("partner_id")
        if not partner_id:
            partner_id = backend.execute_user_id.partner_id.id

        # Resolve journal: use provided or find the first sales journal
        journal_id = invoice_data.get("journal_id")
        if not journal_id:
            journal = self.env["account.journal"].search(
                [("type", "=", "sale"), ("company_id", "=", self.env.company.id)],
                limit=1,
            )
            if not journal:
                raise ValidationError(
                    _("No sales journal found to post Agora invoices")
                )
            journal_id = journal.id

        # Build invoice lines
        line_vals = []
        for line in invoice_data.get("lines", []):
            line_vals.append(
                (
                    0,
                    0,
                    {
                        "name": line.get("name", _("Agora product")),
                        "quantity": line.get("quantity", 1.0),
                        "price_unit": line.get("price_unit", 0.0),
                        "tax_ids": [(6, 0, line.get("tax_ids", []))],
                        "account_id": line.get("account_id"),
                    },
                )
            )

        # Parse invoice date
        invoice_date = invoice_data.get("invoice_date")
        if invoice_date and isinstance(invoice_date, str):
            try:
                invoice_date = datetime.strptime(invoice_date, "%Y-%m-%d").date()
            except ValueError:
                invoice_date = False

        # Parse business day
        business_day = invoice_data.get("agora_business_day")
        if business_day and isinstance(business_day, str):
            try:
                business_day = datetime.strptime(business_day, "%Y-%m-%d").date()
            except ValueError:
                business_day = False

        # Step 1: create the real account.move with all its lines
        # invoice_payment_term_id is required so Odoo can auto-set the due date
        # on the receivable line (enforced by account_payment_partner)
        payment_term = self.env["account.payment.term"].search(
            [("company_id", "in", [self.env.company.id, False])], limit=1
        )
        move_vals = {
            "move_type": invoice_data.get("move_type", "out_invoice"),
            "partner_id": partner_id,
            "journal_id": journal_id,
            "invoice_date": invoice_date,
            "invoice_payment_term_id": payment_term.id if payment_term else False,
            "ref": invoice_data.get("ref")
            or "{} {}".format(
                invoice_data.get("agora_series", ""),
                invoice_data.get("agora_number", ""),
            ).strip(),
            "invoice_line_ids": line_vals,
        }
        if invoice_data.get("currency_id"):
            move_vals["currency_id"] = invoice_data["currency_id"]

        odoo_move = self.env["account.move"].create(move_vals)

        # Step 2: create the agora.account.move binding pointing to the new account.move
        agora_move = AgoraMove.create(
            {
                "odoo_id": odoo_move.id,
                "backend_id": backend.id,
                "agora_invoice_id": invoice_data["agora_invoice_id"],
                "agora_document_type": invoice_data.get(
                    "agora_document_type", "invoice"
                ),
                "agora_workplace_id": invoice_data.get("agora_workplace_id", 0),
                "agora_workplace_name": invoice_data.get("agora_workplace_name", ""),
                "agora_pos_id": invoice_data.get("agora_pos_id", 0),
                "agora_business_day": business_day,
                "agora_series": invoice_data.get("agora_series", ""),
                "agora_number": invoice_data.get("agora_number", ""),
                "agora_customer_id": invoice_data.get("agora_customer_id", ""),
                "import_date": fields.Datetime.now(),
                "source_file": invoice_data.get("source_file", False),
                "raw_data": invoice_data.get("raw_data", False),
            }
        )
        _logger.info(
            "Created Agora invoice %s -> account.move id=%s",
            invoice_data["agora_invoice_id"],
            odoo_move.id,
        )
        return agora_move

    def action_view_odoo_invoice(self):
        """Open the related account.move form from the Agora binding"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "res_id": self.odoo_id.id,
            "view_mode": "form",
            "target": "current",
        }
