# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

import tempfile
import binascii
from odoo.exceptions import UserError
from odoo import _, models, fields
import logging
import xlrd
import io
import base64

_logger = logging.getLogger(__name__)


class ImportChartAccount(models.TransientModel):
    _name = "import.chart.account"
    _description = "Chart of Account"

    company_id = fields.Many2one(
        string="Company",
        help="The company for folio",
        required=True,
        comodel_name="res.company",
    )
    File_select = fields.Binary(string="Select Excel File")

    def import_file(self):
        try:
            fp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            fp.write(binascii.a2b_base64(self.File_select))
            fp.seek(0)
            values = {}
            workbook = xlrd.open_workbook(fp.name)
            sheet = workbook.sheet_by_index(0)
        except UserError:
            raise UserError(_("Invalid file!"))

        for row_no in range(sheet.nrows):
            values = {}
            line = list(map(lambda row: isinstance(row.value, bytes) and row.value.encode(
                'utf-8') or str(row.value), sheet.row(row_no)))
            values.update({
                'code': line[0],
                'name': line[1],
            })

            res = self.create_chart_accounts(values)
        accounts = self.env['account.account'].search([
            ('company_id', '=', self.company_id.id)]
        )
        for account in accounts:
            if len(account.code) < 11:
                zeros = ''
                for i in range(len(account.code), 11):
                    zeros += '0'
                account.code = account.code[:4] + zeros + account.code[-2:]
        return res

    def create_chart_accounts(self, values):

        if values.get("code") == "":
            raise UserError(_('Code field cannot be empty.'))

        if values.get("name") == "":
            raise UserError(_('Name field cannot be empty.'))

        if values.get("code"):
            s = str(values.get("code"))
            code_no = s.rstrip('0').rstrip('.') if '.' in s else s

        account_obj = self.env['account.account']
        account_found = False
        account_founds = account_obj.search([
            ('code', 'ilike', code_no[:4]),
            ('company_id', '=', self.company_id.id)]
        )
        for account in account_founds:
            if (
                account.code[:4] == code_no[:4]
            ):
                account_found = account
                break
        if account_found and len(account_found.code) < 10 and code_no[-2:] == account_found.code[-2:] and code_no[4:-2] == '00000':
            _logger.info("Found Account: From %s to %s", account_found.code, code_no)
            account_found.code = code_no
            account_found.name = values.get("name")
        elif account_found:
            new_account = account_found.copy()
            new_account.code = code_no
            new_account.name = values.get("name")
            _logger.info("Create from reference Account: %s -> %s", account_found.code, new_account.code)
        else:
            _logger.info("Account Reference not found: %s", code_no)

        return True
