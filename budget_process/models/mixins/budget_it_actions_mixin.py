# Copyright 2025 Alexandra Suarez Graterol (Alda hotels) <saya.alex20@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class BudgetItActionsMixin(models.AbstractModel):
    "Mixin for IT budget actions"

    _name = "budget.it.actions.mixin"
    _description = "Budget IT Actions Mixin"
    _inherit = "budget.rooms.base.actions.mixin"

    def action_refresh_rooms_available(self):
        return self.action_refresh_rooms_available_base("[IT]")

    def action_sync_all_rooms_available(self):
        return self.action_sync_all_rooms_available_base("[IT]")

    def action_show_sync_status(self):
        return self.action_show_sync_status_base("[IT]")

    def action_diagnose_current_records(self):
        return self.action_diagnose_current_records_base("[IT]")

    def action_fix_sync_problems(self):
        return self.action_fix_sync_problems_base("[IT]")
