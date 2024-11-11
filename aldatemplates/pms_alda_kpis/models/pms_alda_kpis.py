# Copyright 2024 OsoTranquilo - José Luis Algara
# Copyright 2024 Irlui Ramírez
# From Consultores Hoteleros Integrales (ALDA Hotels) - 2024
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class PMSAldaKpis(models.Model):
    _name = "pms.alda.kpis"
    _description = "Attribute to calculate Alda Kpi"
    
    name = fields.Selection(
        string="Attribute Name Kpi",
        selection=[
            ("ramp_time", "Ramp Up Time"),
            ("another_type", "Another Type"), 
        ],
        required=True,
        help="Specify the name of the KPI attribute.",
    )
    
    kpi_value = fields.Char(
        string='Attribute Value Kpi',
        required=True,
        help="Specify the atrribute value of the KPI. In case Ramp Up Time, value are months from open date",
    )

    @api.constrains('name', 'kpi_value')
    def _check_unique_name_and_value(self):
        for record in self:
            existing_kpi = self.search([('name', '=', record.name), ('id', '!=', record.id)])
            if existing_kpi:
                raise ValidationError(f"A KPI with the name '{record.name}' already exists. You can only modify the existing one.")
            if record.name == 'ramp_time':
                try:
                    int(record.kpi_value)
                except ValueError:
                    raise ValidationError("The kpi_value for 'Ramp-Rate' must be an integer.")

    @api.model
    def get_available_kpi_names(self):
        all_kpis = ["ramp_time", "another_type"]
        used_kpis = self.search([]).mapped('name')
        available_kpis = [(kpi, kpi.replace('_', ' ').title()) for kpi in all_kpis if kpi not in used_kpis]
        return available_kpis