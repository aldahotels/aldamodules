# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

from ..budget_base import MONTHLY_FIELDS

_logger = logging.getLogger(__name__)


class BudgetRevenueRnActionsMixin(models.AbstractModel):
    "Mixin for Room Nights (RN) related actions"
    _name = "budget.revenue.rn.actions.mixin"
    _description = "Budget Revenue RN Actions Mixin"

    def action_refresh_room_nights(self):
        "Refresh room nights from budget.data with fiscal year logic"
        updated_count = 0

        for record in self:
            if record._is_room_nights_budgeted():
                if not (record.fiscal_year_id and record.hotel):
                    _logger.warning(
                        "Record %s missing fiscal_year_id or hotel, skipping sync",
                        record.id,
                    )
                    continue

                old_values = {month: getattr(record, month) for month in MONTHLY_FIELDS}
                record._compute_monthly_amounts()
                new_values = {month: getattr(record, month) for month in MONTHLY_FIELDS}

                if old_values != new_values:
                    updated_count += 1
                    _logger.info(
                        "Updated record %s: %s fiscal %s",
                        record.id,
                        record.hotel.name,
                        record.fiscal_year_id.name,
                    )

        message = "Room nights sync completed. Updated %s records." % updated_count
        _logger.info(message)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Room Nights Sync",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_all_room_nights(self):
        "Server action to sync all room nights records in bulk"
        room_nights_records = self.filtered(lambda r: r._is_room_nights_budgeted())

        if not room_nights_records:
            message = "No room nights budgeted records found to sync."
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Room Nights Bulk Sync",
                    "message": message,
                    "type": "warning",
                    "sticky": False,
                },
            }

        updated_count = 0
        for record in room_nights_records:
            if record.fiscal_year_id and record.hotel:
                old_values = {month: getattr(record, month) for month in MONTHLY_FIELDS}
                record._compute_monthly_amounts()
                new_values = {month: getattr(record, month) for month in MONTHLY_FIELDS}

                if old_values != new_values:
                    updated_count += 1

        message = "RN sync completed. Updated %s of %s records." % (
            updated_count,
            len(room_nights_records),
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Room Nights Bulk Sync",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
