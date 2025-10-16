from odoo import api, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)

        for employee in employees:
            if employee.job_id and employee.active and employee.user_id:
                self.env["helpdesk.team"]._update_team_members_from_employee(employee)

        return employees

    def write(self, vals):
        result = super().write(vals)

        relevant_fields = {"job_id", "active", "user_id", "property_ids"}

        if any(field in vals for field in relevant_fields):
            for employee in self:
                if employee.job_id and employee.active and employee.user_id:
                    self.env["helpdesk.team"]._update_team_members_from_employee(
                        employee
                    )

        return result
