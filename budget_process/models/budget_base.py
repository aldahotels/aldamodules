# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


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
        except Exception:
            pass
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
