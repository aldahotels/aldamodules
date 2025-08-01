from odoo import api, fields, models


class PmsDailyKpiShow(models.TransientModel):
    _name = "pms.daily.kpi.show"
    _description = "Temporal view to show daily KPIs"

    kpi_id = fields.Many2one(
        "pms.daily.kpi", string="Daily KPI", required=True, ondelete="cascade"
    )

    date_today = fields.Date(related="kpi_id.date", string="Date", readonly=True)
    pms_property_id = fields.Many2one(
        related="kpi_id.pms_property_id", string="Property", readonly=True
    )
    total_rooms = fields.Integer(
        related="kpi_id.total_rooms", string="Total Rooms", readonly=True
    )
    occupied_rooms = fields.Integer(
        related="kpi_id.occupied_rooms", string="Occupied Rooms", readonly=True
    )
    pax = fields.Integer(
        related="kpi_id.pax",
        string="Pax",
        readonly=True,
    )
    blocked_rooms = fields.Integer(
        related="kpi_id.blocked_rooms", string="Blocked Rooms", readonly=True
    )
    available_rooms = fields.Integer(
        related="kpi_id.available_rooms", string="Available Rooms", readonly=True
    )
    occupancy_rate = fields.Float(
        related="kpi_id.occupancy_rate", string="Occupancy Rate (%)", readonly=True
    )
    block_rate = fields.Float(
        related="kpi_id.block_rate", string="Block Rate (%)", readonly=True
    )
    adr = fields.Float(related="kpi_id.adr", string="Average Daily Rate", readonly=True)
    revpar = fields.Float(related="kpi_id.revpar", string="RevPAR", readonly=True)

    @api.onchange("date_today", "pms_property_id")
    def _onchange_load_kpi_data(self):
        for record in self:
            if not record.pms_property_id or not record.date_today:
                record.update(
                    {
                        "total_rooms": 0,
                        "occupied_rooms": 0,
                        "blocked_rooms": 0,
                        "pax": 0,
                        "available_rooms": 0,
                        "occupancy_rate": 0.0,
                        "block_rate": 0.0,
                        "adr": 0.0,
                    }
                )
                continue

            kpi = self.env["pms.daily.kpi"].create_or_update_daily_kpi(
                record.pms_property_id.id, record.date_today
            )

            record.update(
                {
                    "total_rooms": kpi.total_rooms,
                    "occupied_rooms": kpi.occupied_rooms,
                    "blocked_rooms": kpi.blocked_rooms,
                    "pax": kpi.pax,
                    "available_rooms": kpi.available_rooms,
                    "occupancy_rate": kpi.occupancy_rate,
                    "block_rate": kpi.block_rate,
                    "adr": kpi.adr,
                }
            )
