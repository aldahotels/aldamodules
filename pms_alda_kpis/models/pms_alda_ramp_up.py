# Copyright 2024 OsoTranquilo - José Luis Algara
# Copyright 2024 Irlui Ramírez
# From Consultores Hoteleros Integrales (ALDA Hotels) - 2024
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime

class PmsProperty(models.Model):
    _inherit = "pms.property"

    is_ramp_up = fields.Boolean(
        string='Ramp-Up', 
        compute='_compute_state', 
        default=False,
        help="From the opening of a hotel the first 17 months a hotel has RAMP-UP status, from month 17 it has RAMP-RATE status.",
    )
    
    is_ramp_rate = fields.Boolean(
        string='Ramp-Rate', 
        compute='_compute_state',
        default=False,
        help="From the opening of a hotel the first 17 months a hotel has RAMP-UP status, from month 17 it has RAMP-RATE status.",
    )

    months_to_ramp_rate = fields.Integer(
        string='Month to Ramp-Rate', 
        compute='_compute_months_to_ramp_rate',
        help="From the opening of a hotel the first 17 months a hotel has RAMP-UP status, from month 17 it has RAMP-RATE status.",
    )

    @api.model
    def _compute_state(self):
        for record in self:
            if record.open_date:
                open_date = fields.Date.from_string(record.open_date)
                today = fields.Date.context_today(self)
                #today = fields.Date.today()
                diff_months = (today.year - open_date.year) * 12 + today.month - open_date.month
                kpi_value = self.env['pms.alda.kpis'].search([('name', '=', 'ramp_time')])
                record.is_ramp_up = diff_months < int(kpi_value.kpi_value)
                record.is_ramp_rate = diff_months >= int(kpi_value.kpi_value)
            else:
                record.is_ramp_up = False
                record.is_ramp_rate = False

    @api.model
    def _compute_months_to_ramp_rate(self):
        for record in self:
            if record.open_date:
                open_date = fields.Date.from_string(record.open_date)
                today = fields.Date.context_today(self)
                diff_months = (today.year - open_date.year) * 12 + today.month - open_date.month
                kpi_value = self.env['pms.alda.kpis'].search([('name', '=', 'ramp_time')])
                if diff_months < int(kpi_value.kpi_value):
                    record.months_to_ramp_rate = int(kpi_value.kpi_value) - diff_months
                else:
                    record.months_to_ramp_rate = 0
            else:
                record.months_to_ramp_rate = 0
