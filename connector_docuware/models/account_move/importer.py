# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import base64

from odoo import _
from odoo.exceptions import ValidationError

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping


class DocuwareImporter(Component):
    _name = "docuware.account.move.importer"
    _inherit = "docuware.document.importer"
    _apply_on = "docuware.account.move"

    def _after_import(self, binding):
        attachment = self.backend_adapter.get_document_attachment(
            binding.cabinet_id.docuware_id, binding.docuware_id
        )
        self.env["ir.attachment"].sudo().create(
            {
                "res_model": "account.move",
                "res_id": binding.odoo_id.id,
                "datas": base64.b64encode(attachment),
                "mimetype": "application/pdf",
                "type": "binary",
                "name": "{}.pdf".format(binding.ref),
            }
        )
        return super()._after_import(binding)

    def _create(self, data):
        binding = super()._create(data)
        if binding.partner_not_found:
            binding.odoo_id.message_post(
                body=_("Supplier with vat {}  not found").format(
                    data.get("docuware_vat")
                ),
                message_type="comment",
            )
        return binding


class DocuwareMapper(Component):
    _name = "docuware.account.move.mapper"
    _inherit = "docuware.import.mapper"
    _apply_on = "docuware.account.move"

    direct = [
        ("Id", "docuware_id"),
        ("NUMERO_DOCUMENTO", "ref"),
        ("NUMERO_DOCUMENTO", "payment_reference"),
        ("IMPORTE_TOTAL", "docuware_amount_total"),
        ("FECHA", "invoice_date"),
        ("VENCIMIENTO", "invoice_date_due"),
        ("TIPO_DOCUMENTO", "docuware_document_type"),
        ("CIF_PROVEEDOR", "docuware_vat"),
    ]

    @mapping
    def company_id(self, record):
        company = self.backend_record.map_company(record.get("SOCIEDAD"))
        if not company:
            raise ValidationError(
                _("Company with name {} not found").format(record.get("SOCIEDAD"))
            )
        return {"company_id": company.id}

    @mapping
    def pms_property_id(self, record):
        property_rec = self.backend_record.map_property(record.get("HOTEL_RECEPTOR"))
        return {"pms_property_id": property_rec.id}

    @mapping
    def payment_mode_id(self, record):
        if not record.get("FORMA_DE_PAGO"):
            return {}
        payment_mode = self.backend_record.with_company(
            self.backend_record.map_company(record.get("SOCIEDAD"))
        ).map_payment_mode(record.get("FORMA_DE_PAGO"))
        if not payment_mode:
            raise ValidationError(
                _("Payment mode with name {} for the company {} not found").format(
                    record.get("FORMA_DE_PAGO"), record.get("SOCIEDAD")
                )
            )
        return {"payment_mode_id": payment_mode.id}

    @mapping
    def partner_id(self, record):
        partner_vat = record.get("CIF_PROVEEDOR")
        if not partner_vat:
            raise ValidationError(_("Vat not informed"))
        partner = (
            self.env["res.partner"]
            .search(
                ["|", ("vat", "=", partner_vat), ("vat", "=", "ES" + partner_vat)],
                limit=1,
            )
            .commercial_partner_id
        )
        if not partner:
            return {"partner_not_found": True}
        bank_acc = False
        if record.get("IBAN"):
            bank_acc = self.env["res.partner.bank"].search(
                [
                    ("partner_id", "=", partner.id),
                    ("acc_number", "=", record.get("IBAN")),
                    (
                        "company_id",
                        "=",
                        self.backend_record.map_company(record.get("SOCIEDAD")).id,
                    ),
                ],
                limit=1,
            )
            if not bank_acc:
                bank_acc = self.env["res.partner.bank"].create(
                    {
                        "partner_id": partner.id,
                        "acc_number": record.get("IBAN"),
                        "company_id": self.backend_record.map_company(
                            record.get("SOCIEDAD")
                        ).id,
                    }
                )
        return {"partner_id": partner.id, "partner_bank_id": bank_acc}

    @mapping
    def move_type(self, record):
        return {"move_type": "in_invoice"}

    @mapping
    def docuware_fixed_asset(self, record):
        return {"docuware_fixed_asset": record.get("INMOBILIZADO") == "Si"}

    @mapping
    def cabinet_id(self, record):
        cabinet = self.env["docuware.cabinet"].search(
            [("docuware_id", "=", record.get("FileCabinetId"))]
        )
        return {"cabinet_id": cabinet.id}

    def finalize(self, map_record, values):

        source_vals = map_record.source
        partner_id = values.get("partner_id")
        company_id = values.get("company_id")
        property_id = values.get("pms_property_id")
        move_type = values.get("move_type")
        context = dict(self.env.context)
        context["default_pms_property_id"] = property_id
        if move_type:
            context["default_move_type"] = move_type
        if company_id:
            context["default_company_id"] = company_id
            context["allowed_company_ids"] = [company_id]
        journal = self.env["account.move"].with_context(context)._get_default_journal()
        values["journal_id"] = journal.id
        onchange_values = (
            self.env["account.move"]
            .with_context(context)
            .play_onchanges(
                {
                    "partner_id": partner_id,
                    "move_type": move_type,
                    "journal_id": journal.id,
                },
                ["partner_id"],
            )
        )
        for key in onchange_values.keys():
            if key not in values:
                if key == "invoice_payment_term_id" and values.get("invoice_date_due"):
                    continue
                values[key] = onchange_values[key]

        if partner_id:
            previous_invoice = self.env["account.move"].search(
                [
                    ("move_type", "=", "in_invoice"),
                    ("partner_id", "=", partner_id),
                    ("state", "!=", "draft"),
                    ("company_id", "=", company_id),
                    ("journal_id", "=", journal.id),
                ],
                order="invoice_date desc",
                limit=1,
            )
        else:
            previous_invoice = self.env["account.move"]

        new_lines = []
        for line in previous_invoice.invoice_line_ids:
            new_line_data = line.copy_data(
                default={
                    "asset_id": False,
                    "price_unit": 0.0,
                    "pms_property_id": values.get("pms_property_id"),
                }
            )[0]
            new_line_data.pop("move_id")
            new_lines.append(new_line_data)

        if source_vals["TIPO_DOCUMENTO"] == "Factura":
            for detail_line in source_vals.get("DETALLES"):
                tax_name = detail_line.get("DETAL_NOMBRE_IMPUESTO")
                tax = self.env["account.tax"].search(
                    [("name", "=", tax_name), ("company_id", "=", company_id)]
                )
                if tax_name and not tax:
                    continue
                if tax:
                    assigned_line = False
                    for line_data in new_lines:
                        if (
                            line_data.get("tax_ids")
                            and tax.id in line_data["tax_ids"][0][2]
                        ):
                            line_data["price_unit"] = detail_line.get("DETAL_BASE")
                            assigned_line = True
                    if not assigned_line:
                        new_lines.append(
                            {
                                "tax_ids": [(6, 0, [tax.id])],
                                "price_unit": detail_line.get("DETAL_BASE"),
                            }
                        )
        else:
            if new_lines:
                new_lines[0]["price_unit"] = source_vals.get("IMPORTE_TOTAL")
            else:
                new_lines.append({"price_unit": source_vals.get("IMPORTE_TOTAL")})

        values["invoice_line_ids"] = [(0, 0, x) for x in new_lines]
        return values
