# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2018 Alexandre Díaz <dev@redneboa.es>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from io import BytesIO
import xlsxwriter
from itertools import cycle

import base64
import json
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GlassofExporterWizard(models.TransientModel):
    FILENAME = "invoices_glasof.xls"
    _name = "glasof.exporter.wizard"

    date_start = fields.Date("Start Date")
    date_end = fields.Date("End Date")
    export_journals = fields.Boolean("Export Account Movements?", default=True)
    export_invoices = fields.Boolean("Export Invoices?", default=True)
    property_ids = fields.Many2many(
        string="Properties", comodel_name="pms.property"
    )
    company_id = fields.Many2one(
        string="Company",
        help="The company",
        required=True,
        comodel_name="res.company",
    )
    journal_ids = fields.Many2many(
        string="Journals",
        help="Journals to include in the report",
        comodel_name="account.journal",
        relation="glasof_exporter_wizard_journal_rel",
        column1="wizard_id",
        column2="journal_id",
        domain="[('pms_property_ids', 'in', property_ids),('company_id', '=', company_id),('type', 'in', ['sale', 'purchase'])]",
    )
    seat_num = fields.Integer("Seat Number Start", default=1)
    xls_journals_filename = fields.Char()
    xls_journals_binary = fields.Binary()
    xls_invoices_filename = fields.Char()
    xls_invoices_binary = fields.Binary()

    @api.onchange("company_id")
    def onchange_property_id(self):
        if (
            self.property_ids
            and self.company_id
            and any(x.company_id != self.company_id for x in self.property_ids)
        ):
            raise UserError(
                _(
                    "Alguno de los hoteles seleccionados no es de esta compañía, elimina o modifica los hoteles para seleccionar esta compañía"
                )
            )

    @api.model
    def _export_payments(self):
        file_data = BytesIO()
        workbook = xlsxwriter.Workbook(
            file_data, {"strings_to_numbers": True, "default_date_format": "dd/mm/yyyy"}
        )

        company_id = self.env.user.company_id
        workbook.set_properties(
            {
                "title": "Exported data from " + company_id.name,
                "subject": "PMS Data from Odoo of " + company_id.name,
                "author": "Odoo ALDA PMS",
                "manager": "Jose Luis Algara",
                "company": company_id.name,
                "category": "Hoja de Calculo",
                "keywords": "pms, odoo, alda, data, " + company_id.name,
                "comments": "Created with Python in Odoo and XlsxWriter",
            }
        )
        workbook.use_zip64()

        xls_cell_format_header = workbook.add_format({"bg_color": "#000000", "font_color": "#FFFFFF"})

        worksheet = workbook.add_worksheet("Simples-1")

        worksheet.write("A1", _("Diario"), xls_cell_format_header)
        worksheet.write("B1", _("Estado"), xls_cell_format_header)
        worksheet.write("C1", _("Num Factura"), xls_cell_format_header)
        worksheet.write("D1", _("Cliente/Prov."), xls_cell_format_header)
        worksheet.write("E1", _("Origen"), xls_cell_format_header)
        worksheet.write("F1", _("Fecha de Factura"), xls_cell_format_header)
        worksheet.write("G1", _("NIF"), xls_cell_format_header)
        worksheet.write("H1", _("Base Imponible"), xls_cell_format_header)
        worksheet.write("I1", _("Impuestos"), xls_cell_format_header)
        worksheet.write("J1", _("Total"), xls_cell_format_header)
        worksheet.write("K1", _("Pendiente"), xls_cell_format_header)
        worksheet.write("L1", _("Tipo"), xls_cell_format_header)
        worksheet.write("M1", _("Pagos"), xls_cell_format_header)
        worksheet.write("N1", _("Importe"), xls_cell_format_header)
        worksheet.write("O1", _("Fecha"), xls_cell_format_header)
        worksheet.write("P1", _("Referencia"), xls_cell_format_header)

        worksheet.set_column("A:A", 25)
        worksheet.set_column("B:B", 10)
        worksheet.set_column("C:C", 25)
        worksheet.set_column("D:D", 50)
        worksheet.set_column("E:E", 15)
        worksheet.set_column("F:F", 15)
        worksheet.set_column("G:G", 15)
        worksheet.set_column("H:H", 9)
        worksheet.set_column("I:I", 9)
        worksheet.set_column("J:J", 9)
        worksheet.set_column("K:K", 9)
        worksheet.set_column("L:L", 18)
        worksheet.set_column("M:M", 25)
        worksheet.set_column("N:N", 9)
        worksheet.set_column("O:O", 15)
        worksheet.set_column("P:P", 20)

        account_inv_obj = self.env["account.move"]
        domain = [
            ("date", ">=", self.date_start),
            ("date", "<=", self.date_end),
            ("company_id", "=", self.company_id.id),
            ("pms_property_id", "in", self.property_ids.ids if self.property_ids else []),
            ("move_type", "!=", "entry"),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))

        account_invs = account_inv_obj.search(domain, order="name")
        nrow = 1
        xls_cell_format_date1 = workbook.add_format({"num_format": "dd/mm/yyyy", 'bg_color': '#FFFFFF'})
        xls_cell_format_date2 = workbook.add_format({"num_format": "dd/mm/yyyy", 'bg_color': '#CCCCCC'})
        xls_cell_format_money1 = workbook.add_format({"num_format": "#,##0.00", 'bg_color': '#FFFFFF'})
        xls_cell_format_money2 = workbook.add_format({"num_format": "#,##0.00", 'bg_color': '#CCCCCC'})
        data_format1 = workbook.add_format({'bg_color': '#FFFFFF'})
        data_format2 = workbook.add_format({'bg_color': '#CCCCCC'})
        data_formats = cycle([data_format1, data_format2])
        date_formats = cycle([xls_cell_format_date1, xls_cell_format_date2])
        money_formats = cycle([xls_cell_format_money1, xls_cell_format_money2])
        for inv in account_invs:
            data_format = next(data_formats)
            date_format = next(date_formats)
            money_format = next(money_formats)
            country_code = ""
            if inv.partner_id.vat:
                vat_partner = inv.partner_id.vat
            elif inv.partner_id.aeat_identification:
                vat_partner = inv.partner_id.aeat_identification
            country_partner = inv.partner_id.country_id
            if country_partner:
                country_code = country_partner.code
                if inv.partner_id.vat:
                    vat_partner = (
                        inv.partner_id.vat[2:]
                        if inv.partner_id.vat[2:] == country_code
                        else inv.partner_id.vat
                    )

            if not vat_partner and inv.partner_id.vat:
                vat_partner = inv.partner_id.vat
            origin = ""
            if inv.move_type == "out_refund":
                origin = inv.invoice_origin
            elif inv.folio_ids:
                origin = ",".join([fol.name for fol in inv.folio_ids])

            state = inv._fields["state"].selection
            state_dict = dict(state)
            state = state_dict.get(inv.state)

            move_type = inv._fields["move_type"].selection
            move_type_dict = dict(move_type)
            move_type = move_type_dict.get(inv.move_type)
            payments_dict = json.loads(inv.invoice_payments_widget)

            if not payments_dict:
                worksheet.write(nrow, 0, inv.journal_id.name)
                worksheet.write(nrow, 1, state)
                worksheet.write(
                    nrow, 2,
                    inv.move_type in ('in_invoice', 'in_refund') and inv.ref or inv.
                    name)
                worksheet.write(nrow, 3, inv.partner_id.name)
                worksheet.write(nrow, 4, origin)
                worksheet.write(nrow, 5, inv.invoice_date, date_format)
                worksheet.write(nrow, 6, vat_partner)
                worksheet.write(nrow, 7, inv.amount_untaxed, money_format)
                worksheet.write(nrow, 8, inv.amount_tax, money_format)
                worksheet.write(nrow, 9, inv.amount_total, money_format)
                worksheet.write(nrow, 10, inv.amount_residual, money_format)
                worksheet.write(nrow, 11, move_type)
                worksheet.set_row(nrow, cell_format=data_format)
                nrow += 1
            else:
                for payment in payments_dict.get("content"):
                    payment_date = fields.Date.from_string(payment.get("date"))
                    worksheet.write(nrow, 0, inv.journal_id.name)
                    worksheet.write(nrow, 1, state)
                    worksheet.write(
                        nrow, 2, inv.move_type in ('in_invoice', 'in_refund') and inv.
                        ref or inv.name)
                    worksheet.write(nrow, 3, inv.partner_id.name)
                    worksheet.write(nrow, 4, origin)
                    worksheet.write(nrow, 5, inv.invoice_date, date_format)
                    worksheet.write(nrow, 6, vat_partner)
                    worksheet.write(nrow, 7, inv.amount_untaxed, money_format)
                    worksheet.write(nrow, 8, inv.amount_tax, money_format)
                    worksheet.write(nrow, 9, inv.amount_total, money_format)
                    worksheet.write(nrow, 10, inv.amount_residual, money_format)
                    worksheet.write(nrow, 11, move_type)
                    worksheet.write(nrow, 12, payment["journal_name"])
                    worksheet.write(nrow, 13, payment["amount"], money_format)
                    worksheet.write(nrow, 14, payment_date, date_format)
                    worksheet.write(nrow, 15, payment["ref"])
                    worksheet.set_row(nrow, cell_format=data_format)
                    nrow += 1
        workbook.close()
        file_data.seek(0)
        tnow = str(fields.Datetime.now()).replace(" ", "_")
        return {
            "xls_journals_filename": "pagos_facturas_%s.xlsx" % tnow,
            "xls_journals_binary": base64.encodestring(file_data.read()),
        }

    @api.model
    def _export_invoices(self):
        file_data = BytesIO()
        workbook = xlsxwriter.Workbook(
            file_data, {"strings_to_numbers": True, "default_date_format": "dd/mm/yyyy"}
        )

        company_id = self.env.user.company_id
        workbook.set_properties(
            {
                "title": "Exported data from " + company_id.name,
                "subject": "PMS Data from Odoo of " + company_id.name,
                "author": "Odoo ALDA PMS",
                "manager": "Jose Luis Algara",
                "company": company_id.name,
                "category": "Hoja de Calculo",
                "keywords": "pms, odoo, alda, data, " + company_id.name,
                "comments": "Created with Python in Odoo and XlsxWriter",
            }
        )
        workbook.use_zip64()

        xls_cell_format_date = workbook.add_format({"num_format": "dd/mm/yyyy"})
        xls_cell_format_money = workbook.add_format({"num_format": "#,##0.00"})
        xls_cell_format_odec = workbook.add_format({"num_format": "#,#0.0"})

        worksheet = workbook.add_worksheet("ventas")

        account_inv_obj = self.env["account.move"]
        domain = [
            ("date", ">=", self.date_start),
            ("date", "<=", self.date_end),
            ("move_type", "!=", "entry"),
            ("company_id", "=", self.company_id.id),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.property_ids:
            domain.append(("pms_property_id", "in", self.property_ids.ids))
        account_invs = account_inv_obj.search(domain)
        nrow = 1
        for inv in account_invs:
            if inv.partner_id.parent_id:
                lastname = inv.partner_id.parent_id.name or ""
                firstname = ""
            elif inv.partner_id.is_company:
                lastname = inv.partner_id.name
                firstname = ""
            else:
                lastname = inv.partner_id.lastname or ""
                firstname = inv.partner_id.firstname or ""

            country_code = ""
            vat_partner = inv.partner_id.vat if inv.partner_id.vat else ""
            country_partner = inv.partner_id.country_id
            if country_partner:
                country_code = country_partner.code
                if inv.partner_id.vat:
                    vat_partner = (
                        inv.partner_id.vat[2:]
                        if inv.partner_id.vat[2:] == country_code
                        else inv.partner_id.vat
                    )

            if not vat_partner and inv.partner_id.vat:
                vat_partner = inv.partner_id.vat

            worksheet.write(
                nrow, 0, inv.move_type in ('in_invoice', 'in_refund') and inv.
                ref or inv.name)
            worksheet.write(nrow, 1, inv.invoice_date, xls_cell_format_date)
            worksheet.write(nrow, 2, "")
            worksheet.write(nrow, 3, country_code)
            worksheet.write(nrow, 4, vat_partner)
            worksheet.write(nrow, 5, lastname)
            worksheet.write(nrow, 6, "")
            worksheet.write(nrow, 7, firstname)
            worksheet.write(nrow, 8, 705.0, xls_cell_format_odec)
            worksheet.write(nrow, 9, inv.amount_untaxed, xls_cell_format_money)
            if any(inv.line_ids.tax_line_id):
                worksheet.write(
                    nrow,
                    10,
                    sum(inv.line_ids.tax_line_id.mapped("amount")),
                    xls_cell_format_money,
                )
            else:
                worksheet.write(nrow, 10, "")
            worksheet.write(
                nrow, 11, inv.amount_tax and inv.amount_tax or "", xls_cell_format_money
            )
            worksheet.write(nrow, 12, "")
            worksheet.write(nrow, 13, "")
            worksheet.write(nrow, 14, "")
            worksheet.write(nrow, 15, "")
            worksheet.write(nrow, 16, "")
            worksheet.write(nrow, 17, "")
            worksheet.write(nrow, 18, "")
            worksheet.write(nrow, 19, "")
            worksheet.write(nrow, 20, "")
            worksheet.write(nrow, 21, "S")
            worksheet.write(nrow, 22, "")
            if inv.move_type == "out_refund":
                worksheet.write(nrow, 23, inv.invoice_origin)
            else:
                worksheet.write(nrow, 23, "")
            worksheet.write(nrow, 24, "")
            worksheet.write(nrow, 25, "")
            worksheet.write(nrow, 27, "")
            worksheet.write(nrow, 28, "")
            worksheet.write(nrow, 29, "")
            worksheet.write(nrow, 30, "")
            worksheet.write(nrow, 31, "")
            worksheet.write(nrow, 32, "")
            worksheet.write(nrow, 33, "")
            worksheet.write(nrow, 34, "")
            worksheet.write(nrow, 35, "")
            worksheet.write(nrow, 36, "")
            worksheet.write(nrow, 37, "")
            worksheet.write(nrow, 38, "")
            worksheet.write(nrow, 39, "")
            worksheet.write(nrow, 40, "")
            worksheet.write(nrow, 41, "")
            worksheet.write(nrow, 42, "")
            worksheet.write(nrow, 43, "430")
            nrow += 1

        workbook.add_worksheet("compras")
        workbook.close()
        file_data.seek(0)
        tnow = str(fields.Datetime.now()).replace(" ", "_")
        return {
            "xls_invoices_filename": "facturas_glasof_%s.xlsx" % tnow,
            "xls_invoices_binary": base64.encodestring(file_data.read()),
        }

    def export(self):
        towrite = {}
        if self.export_journals:
            towrite.update(self._export_payments())
        if self.export_invoices:
            towrite.update(self._export_invoices())
        if any(towrite):
            self.write(towrite)
        return {
            "name": _("Glasof export"),
            "res_id": self.id,
            "res_model": "glasof.exporter.wizard",
            "type": "ir.actions.act_window",
            "view_id": self.env.ref("glasof_exporter.view_glasof_exporter_wizard").id,
            "view_mode": "form",
        }
