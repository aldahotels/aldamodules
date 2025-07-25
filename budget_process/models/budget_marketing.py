# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BudgetMarketing(models.Model):
    _name = "budget.marketing"
    _description = "Marketing budget"
    _inherit = "budget.base"

    department = fields.Selection(
        [("marketing", "Marketing")],
        default="marketing",
        readonly=True,
    )

    # Campos calculados desde contabilidad (equivalentes a las fórmulas en documents)
    oct_actual = fields.Float(
        string="Oct (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for October",
    )
    nov_actual = fields.Float(
        string="Nov (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for November",
    )
    dec_actual = fields.Float(
        string="Dec (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for December",
    )
    jan_actual = fields.Float(
        string="Jan (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for January",
    )
    feb_actual = fields.Float(
        string="Feb (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for February",
    )
    mar_actual = fields.Float(
        string="Mar (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for March",
    )
    apr_actual = fields.Float(
        string="Apr (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for April",
    )
    may_actual = fields.Float(
        string="May (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for May",
    )
    jun_actual = fields.Float(
        string="Jun (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for June",
    )
    jul_actual = fields.Float(
        string="Jul (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for July",
    )
    aug_actual = fields.Float(
        string="Aug (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for August",
    )
    sep_actual = fields.Float(
        string="Sep (Actual)",
        compute="_compute_monthly_accounting_data",
        store=True,
        help="Real accounting balance for September",
    )

    total_actual = fields.Float(
        string="Total Actual",
        compute="_compute_total_actual",
        store=True,
        help="Total real expenses/income for the year",
    )

    # Calcular los datos mensuales reales desde contabilidad
    @api.depends("hotel", "year", "accounting_account")
    def _compute_monthly_accounting_data(self):
        for record in self:
            months = [
                "oct",
                "nov",
                "dec",
                "jan",
                "feb",
                "mar",
                "apr",
                "may",
                "jun",
                "jul",
                "aug",
                "sep",
            ]

            if not record.hotel or not record.year or not record.accounting_account:
                for month in months:
                    setattr(record, f"{month}_actual", 0.0)
                continue

            try:
                year_int = int(record.year)
                monthly_data = record._get_monthly_balance_from_accounting(
                    record.hotel.id, record.accounting_account, year_int
                )

                # Asignar valores a cada campo mensual
                for month, balance in monthly_data.items():
                    setattr(record, f"{month}_actual", balance)

            except Exception as e:
                _logger.warning(
                    f"Error obtaining monthly accounting data for "
                    f"{record.hotel.name} {record.year}: {e}"
                )
                for month in months:
                    setattr(record, f"{month}_actual", 0.0)

    @api.depends(
        "oct_actual",
        "nov_actual",
        "dec_actual",
        "jan_actual",
        "feb_actual",
        "mar_actual",
        "apr_actual",
        "may_actual",
        "jun_actual",
        "jul_actual",
        "aug_actual",
        "sep_actual",
    )
    def _compute_total_actual(self):
        for record in self:
            record.total_actual = sum(
                [
                    record.oct_actual,
                    record.nov_actual,
                    record.dec_actual,
                    record.jan_actual,
                    record.feb_actual,
                    record.mar_actual,
                    record.apr_actual,
                    record.may_actual,
                    record.jun_actual,
                    record.jul_actual,
                    record.aug_actual,
                    record.sep_actual,
                ]
            )

    # Obtiene los balances contables por mes
    def _get_monthly_balance_from_accounting(self, property_id, account_code, year):
        AccountMoveLine = self.env["account.move.line"]
        monthly_data = {}

        month_mapping = {
            "oct": 10,
            "nov": 11,
            "dec": 12,
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
        }

        for month_name, month_num in month_mapping.items():
            try:
                if month_num >= 10:  # Oct, Nov, Dec
                    query_year = year - 1
                else:
                    query_year = year

                date_from = date(query_year, month_num, 1)

                if month_num == 12:
                    date_to = date(query_year + 1, 1, 1) - relativedelta(days=1)
                else:
                    date_to = date(query_year, month_num + 1, 1) - relativedelta(days=1)

                domain = [
                    ("date", ">=", date_from.strftime("%Y-%m-%d")),
                    ("date", "<=", date_to.strftime("%Y-%m-%d")),
                ]

                if hasattr(AccountMoveLine, "property_id"):
                    domain.append(("property_id", "=", property_id))
                elif hasattr(AccountMoveLine, "pms_property_id"):
                    domain.append(("pms_property_id", "=", property_id))

                # Filtrar por cuenta contable
                if account_code:
                    domain.append(("account_id.code", "=", account_code))

                move_lines = AccountMoveLine.search(domain)

                total_balance = -sum(move_lines.mapped("balance"))
                monthly_data[month_name] = total_balance

                _logger.info(
                    f"Marketing {property_id}, {month_name} {query_year}, "
                    f"cuenta {account_code}: {total_balance}"
                )

            except Exception as e:
                _logger.warning(
                    f"Error obtaining accounting data for {month_name} {year}: {e}"
                )
                monthly_data[month_name] = 0.0

        return monthly_data

    # refrescar los datos contables
    def refresh_accounting_data(self):
        self._compute_monthly_accounting_data()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Data Updated",
                "message": "The accounting data has been updated successfully.",
                "type": "success",
                "sticky": False,
            },
        }
