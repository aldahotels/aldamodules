# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BudgetBase(models.AbstractModel):
    _name = "budget.base"
    _description = "Base model for budget process"

    responsible = fields.Char(required=False)
    description = fields.Text()
    accounting_account = fields.Char()
    company_id = fields.Many2one(
        "res.company",
        string="Company",
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

    pms_budget_id = fields.Many2one(
        "pms.budget",
        string="PMS Budget Reference",
        help="Relation with the PMS budget to obtain actual data",
    )

    fiscal_year_id = fields.Many2one(
        "account.fiscal.year",
        string="Fiscal Year",
        help="Select the fiscal year for this budget",
    )

    budget_type = fields.Selection(
        [("budgeted", "Budgeted"), ("real", "Real")],
        required=True,
        default="budgeted",
        help="Indicates if the budget is estimated or real",
    )

    record_type = fields.Selection(
        [
            ("revenue", "Revenue"),
            ("capex", "Capex"),
            ("marketing", "Marketing"),
            ("informatica", "Informatica"),
            ("fb", "Food & Beverage"),
        ],
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

    # Totals
    budgeted_total = fields.Float(compute="_compute_budgeted_total", store=True)
    real_total = fields.Float(compute="_compute_real_total", store=True)
    variance_total = fields.Float(compute="_compute_variance_total", store=True)
    variance_percentage = fields.Float(
        compute="_compute_variance_percentage", store=True
    )

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
        "budget_type",
        "hotel",
        "fiscal_year_id",
        "responsible",
        "record_type",
    )
    def _compute_budgeted_total(self):
        for rec in self:
            if rec.budget_type == "budgeted":
                rec.budgeted_total = sum(
                    [
                        rec.oct or 0.0,
                        rec.nov or 0.0,
                        rec.dec or 0.0,
                        rec.jan or 0.0,
                        rec.feb or 0.0,
                        rec.mar or 0.0,
                        rec.apr or 0.0,
                        rec.may or 0.0,
                        rec.jun or 0.0,
                        rec.jul or 0.0,
                        rec.aug or 0.0,
                        rec.sep or 0.0,
                    ]
                )
            else:
                budgeted_record = self.search(
                    [
                        ("hotel", "=", rec.hotel.id),
                        ("fiscal_year_id", "=", rec.fiscal_year_id.id),
                        ("responsible", "=", rec.responsible),
                        ("record_type", "=", rec.record_type),
                        ("budget_type", "=", "budgeted"),
                    ],
                    limit=1,
                )

                if budgeted_record:
                    rec.budgeted_total = sum(
                        [
                            budgeted_record.oct or 0.0,
                            budgeted_record.nov or 0.0,
                            budgeted_record.dec or 0.0,
                            budgeted_record.jan or 0.0,
                            budgeted_record.feb or 0.0,
                            budgeted_record.mar or 0.0,
                            budgeted_record.apr or 0.0,
                            budgeted_record.may or 0.0,
                            budgeted_record.jun or 0.0,
                            budgeted_record.jul or 0.0,
                            budgeted_record.aug or 0.0,
                            budgeted_record.sep or 0.0,
                        ]
                    )
                else:
                    rec.budgeted_total = 0.0

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
        "budget_type",
        "hotel",
        "fiscal_year_id",
        "responsible",
        "record_type",
    )
    def _compute_real_total(self):
        for rec in self:
            if rec.budget_type == "real":
                rec.real_total = sum(
                    [
                        rec.oct or 0.0,
                        rec.nov or 0.0,
                        rec.dec or 0.0,
                        rec.jan or 0.0,
                        rec.feb or 0.0,
                        rec.mar or 0.0,
                        rec.apr or 0.0,
                        rec.may or 0.0,
                        rec.jun or 0.0,
                        rec.jul or 0.0,
                        rec.aug or 0.0,
                        rec.sep or 0.0,
                    ]
                )
            else:
                real_record = self.search(
                    [
                        ("hotel", "=", rec.hotel.id),
                        ("fiscal_year_id", "=", rec.fiscal_year_id.id),
                        ("responsible", "=", rec.responsible),
                        ("record_type", "=", rec.record_type),
                        ("budget_type", "=", "real"),
                    ],
                    limit=1,
                )

                if real_record:
                    rec.real_total = sum(
                        [
                            real_record.oct or 0.0,
                            real_record.nov or 0.0,
                            real_record.dec or 0.0,
                            real_record.jan or 0.0,
                            real_record.feb or 0.0,
                            real_record.mar or 0.0,
                            real_record.apr or 0.0,
                            real_record.may or 0.0,
                            real_record.jun or 0.0,
                            real_record.jul or 0.0,
                            real_record.aug or 0.0,
                            real_record.sep or 0.0,
                        ]
                    )
                else:
                    rec.real_total = 0.0

    @api.depends("budgeted_total", "real_total")
    def _compute_variance_total(self):
        for rec in self:
            rec.variance_total = (rec.real_total or 0.0) - (rec.budgeted_total or 0.0)

    @api.depends("variance_total", "budgeted_total")
    def _compute_variance_percentage(self):
        for rec in self:
            if rec.budgeted_total and rec.budgeted_total != 0:
                percentage = (rec.variance_total / rec.budgeted_total) * 100.0
                rec.variance_percentage = round(percentage, 2)
                _logger.info(
                    f"Budget {rec.id}: Variance={rec.variance_total}, "
                    f"Budget={rec.budgeted_total}, "
                    f"Percentage={rec.variance_percentage}%"
                )
            else:
                rec.variance_percentage = 0.0

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

    @api.onchange("hotel")
    def _onchange_hotel_sync_company(self):
        if self.hotel:
            company_id = self._get_company_from_pms_property(self.hotel)
            if company_id:
                self.company_id = company_id
            else:
                self.company_id = self.env.company.id

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

        if record.hotel and not record.company_id:
            record._onchange_hotel_sync_company()

        return record

    def write(self, vals):
        result = super().write(vals)
        fields_to_check = {"record_type", "manual_amount", "rooms_available_current"}
        if fields_to_check.intersection(vals.keys()):
            for record in self:
                if hasattr(record, "_compute_monthly_amounts"):
                    record._compute_monthly_amounts()
        return result
