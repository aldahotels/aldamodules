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

    @api.onchange("job_id", "active", "user_id", "property_ids")
    def _onchange_team_membership(self):
        HelpdeskTeam = self.env["helpdesk.team"]

        for emp in self:
            if emp.job_id and emp.active and emp.user_id:
                HelpdeskTeam._sync_team_members_for_employee(emp)
                HelpdeskTeam._sync_team_members_for_employee(emp)
            else:
                HelpdeskTeam._remove_employee_from_teams(emp)

    def write(self, vals):
        result = super().write(vals)

        relevant_fields = {"job_id", "active", "user_id", "property_ids"}

        if any(field in vals for field in relevant_fields):
            HelpdeskTeam = self.env["helpdesk.team"]
            for employee in self:
                if employee.job_id and employee.active and employee.user_id:
                    HelpdeskTeam._update_team_members_from_employee(employee)
                else:
                    HelpdeskTeam._remove_employee_from_teams(employee)

        return result
