# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def get_years():
    year_list = []
    for i in range(2020, 2040):
        year_list.append((str(i), str(i)))
    return year_list


class BudgetBase(models.AbstractModel):
    _name = "budget.base"
    _description = "Base model for budget process"

    responsible = fields.Char(required=False)
    description = fields.Text()
    accounting_account = fields.Char()
    company = fields.Many2one(
        "res.company",
        required=False,
        default=lambda self: self.env.company,
    )
    hotel = fields.Many2one(
        "pms.property",
        required=True,
        default=lambda self: self._get_default_hotel(),
    )
    hotel_code = fields.Char(
        related="hotel.pms_property_code",
        store=True,
        string="Hotel Code",
        readonly=True,
    )
    hotel_id = fields.Char(string="Hotel ID")
    year = fields.Selection(
        get_years(),
        required=True,
        default=lambda self: str(fields.Date.today().year),
    )

    oct = fields.Float()
    nov = fields.Float()
    dec = fields.Float()
    jan = fields.Float()
    feb = fields.Float()
    mar = fields.Float()
    apr = fields.Float()
    may = fields.Float()
    jun = fields.Float()
    jul = fields.Float()
    aug = fields.Float()
    sep = fields.Float()

    total = fields.Float(compute="_compute_total", store=True)

    def _get_default_hotel(self):
        try:
            if (
                hasattr(self.env.user, "get_active_property_ids")
                and self.env.user.get_active_property_ids()
            ):
                active_property_id = self.env.user.get_active_property_ids()[0]
                return active_property_id
        except Exception as e:
            _logger.error(f"Error en _get_default_hotel: {e}")
        return False

    @api.constrains("hotel")
    def _check_hotel(self):
        for record in self:
            if not record.hotel:
                pass

    @api.depends(
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
    )
    def _compute_total(self):
        for rec in self:
            rec.total = sum(
                [
                    rec.oct,
                    rec.nov,
                    rec.dec,
                    rec.jan,
                    rec.feb,
                    rec.mar,
                    rec.apr,
                    rec.may,
                    rec.jun,
                    rec.jul,
                    rec.aug,
                    rec.sep,
                ]
            )

    @api.onchange("hotel")
    def _onchange_hotel_sync_company(self):
        if self.hotel:
            company_id = self._get_company_from_pms_property(self.hotel)
            if company_id:
                self.company = company_id
            else:
                self.company = self.env.company.id

    def _get_company_from_pms_property(self, pms_property):
        if not pms_property:
            return False

        try:
            company_fields = ["company_id", "company", "res_company_id"]

            for field_name in company_fields:
                if hasattr(pms_property, field_name):
                    company_field = getattr(pms_property, field_name)
                    if company_field:
                        if hasattr(company_field, "id"):
                            _logger.info(
                                f"Hotel {pms_property.name}: Company synchronized "
                                f"from {field_name} -> {company_field.name}"
                            )
                            return company_field.id
                        elif isinstance(company_field, int):
                            _logger.info(
                                f"Hotel {pms_property.name}: Company ID synchronized "
                                f"from {field_name} -> {company_field}"
                            )
                            return company_field

            _logger.warning(
                f"Hotel {pms_property.name}: No company field found in PMS property"
            )
            return False

        except Exception as e:
            _logger.error(
                f"Error synchronizing company for hotel {pms_property.name}: {e}"
            )
            return False

    @api.model
    def create(self, vals):
        record = super().create(vals)

        if record.hotel and not record.company:
            record._onchange_hotel_sync_company()

        return record

    def write(self, vals):
        result = super().write(vals)
        fields_to_check = {"record_type", "manual_amount", "rooms_available_current"}
        if fields_to_check.intersection(vals.keys()):
            for record in self:
                record._compute_monthly_amounts()
        return result
