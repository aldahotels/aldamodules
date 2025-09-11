# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class BudgetLoadWizard(models.TransientModel):
    _name = "budget.load.wizard"
    _description = "Load Budget Data by Year"

    year = fields.Selection(
        [
            ("2024", "2024"),
            ("2025", "2025"),
            ("2026", "2026"),
            ("2027", "2027"),
        ],
        required=True,
        default="2025",
    )

    property_ids = fields.Many2many(
        "pms.property", string="Properties", help="Leave empty to load all properties"
    )

    def action_load_budget_data(self):
        """Load budget data from pms.budget into budget.data for year and properties."""

        domain = [("year", "=", self.year)]
        if self.property_ids:
            domain.append(("pms_property_id", "in", self.property_ids.ids))

        pms_budgets = self.env["pms.budget"].search(domain)

        created_count = 0
        updated_count = 0

        for budget in pms_budgets:
            existing = self.env["budget.data"].search(
                [
                    ("pms_property_id", "=", budget.pms_property_id.id),
                    ("year", "=", budget.year),
                    ("month", "=", budget.month),
                ]
            )

            if existing:
                # Handle multiple records by updating all of them
                existing.write(
                    {
                        "room_nights": budget.room_nights,
                        "room_revenue": budget.room_revenue,
                    }
                )
                updated_count += len(existing)
            else:
                self.env["budget.data"].create(
                    {
                        "pms_property_id": budget.pms_property_id.id,
                        "year": budget.year,
                        "month": budget.month,
                        "room_nights": budget.room_nights,
                        "room_revenue": budget.room_revenue,
                    }
                )
                created_count += 1

        # Provide feedback to the user
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"Budget Data Loaded for {self.year}",
                "message": (
                    f"Created {created_count} new records, "
                    f"Updated {updated_count} existing records "
                    "from pms.budget DataBI."
                ),
                "type": "success",
                "sticky": True,
            },
        }
