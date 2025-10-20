from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskTeam(models.Model):
    _inherit = "helpdesk.team"

    assign_by_property = fields.Boolean(
        string="Assign based on Property and Ticket Type",
        store=True,
        default=False,
        help="If selected, tickets will be assigned to employees based, "
        "on the property associated with the ticket.",
    )

    team_job_ids = fields.One2many(
        comodel_name="hr.job",
        inverse_name="ticket_team_id",
        string="Associated Jobs",
        help="Job positions associated with this helpdesk team.",
    )

    def _get_filtered_member_ids(self):
        self.ensure_one()
        if not self.assign_by_property or not self.team_job_ids:
            return self.member_ids.ids

        helpdesk_group = self.env.ref("helpdesk.group_helpdesk_user")
        employees = (
            self.env["hr.employee"]
            .sudo()
            .search(
                [
                    ("job_id", "in", self.team_job_ids.ids),
                    ("property_ids", "!=", False),
                    ("user_id", "!=", False),
                    ("user_id.groups_id", "in", helpdesk_group.id),
                    ("active", "=", True),
                ]
            )
        )
        return list(set(employees.mapped("user_id.id")))

    def _update_team_members_from_employee(self, employee):
        if not employee.user_id or not employee.active:
            return

        teams_to_update = self.search(
            [
                ("assign_by_property", "=", True),
                ("team_job_ids", "in", employee.job_id.ids),
            ]
        )

        for team in teams_to_update:
            team.member_ids = team._get_filtered_member_ids()

    def _get_members_without_assigned_by_property(self):
        self.ensure_one()
        if not self.assign_by_property:
            return self.member_ids
        return self.env["res.users"]

    def get_members_jobs_without_ticket_type(self):
        self.ensure_one()
        if all(not job.ticket_type_ids for job in self.team_job_ids):
            return self.member_ids
        else:
            return self.env["res.users"]

    def _get_members_from_jobs(self, ticket=None, vals=None):
        self.ensure_one()
        context = self.env.context or {}

        property_id = (
            ticket.pms_property_id.id
            if ticket and ticket.pms_property_id
            else vals.get("pms_property_id")
            if vals
            else None
        )
        ticket_type_id = (
            ticket.ticket_type_id.id
            if ticket and ticket.ticket_type_id
            else vals.get("ticket_type_id")
            if vals
            else None
        )

        default_ticket = context.get("default_ticket", {})
        property_id = (
            default_ticket.get("pms_property_id")
            or property_id
            or default_ticket.get("property_id")
        )
        ticket_type_id = default_ticket.get("ticket_type_id") or ticket_type_id
        team_id = default_ticket.get("team_id") or vals.get("team_id")
        team = self.env["helpdesk.team"].browse(team_id) if team_id else self

        users = team.member_ids
        if not users:
            return self.env["res.users"]

        users_filtered = self.env["res.users"]

        candidates = self.get_members_jobs_without_ticket_type()
        if candidates:
            for user in candidates:
                qualifying_employees = user.employee_ids.filtered(
                    lambda e: (
                        e.job_id
                        in self.team_job_ids.filtered(lambda j: not j.ticket_type_ids)
                        and property_id in e.property_ids.ids
                    )
                )

                if qualifying_employees:
                    users_filtered |= user

        if not candidates and ticket_type_id and property_id:
            for user in users:
                employees = user.employee_ids.filtered(
                    lambda e: e.job_id.id in self.team_job_ids.ids
                )

                for emp in employees:
                    job = emp.job_id
                    if job.ticket_type_ids and ticket_type_id:
                        if ticket_type_id in job.ticket_type_ids.ids:
                            if property_id and property_id in emp.property_ids.ids:
                                users_filtered |= user
                                break
                    elif not job.ticket_type_ids:
                        if property_id and property_id in emp.property_ids.ids:
                            users_filtered |= user
                            break

        return users_filtered

    @api.onchange("assign_by_property", "team_job_ids", "member_ids")
    def _onchange_assign_by_property(self):
        for team in self:
            if team.assign_by_property and not team.team_job_ids:
                team.assign_by_property = False
                return {
                    "warning": {
                        "title": _("Missing Jobs"),
                        "message": _(
                            "You must associate at least one job with the team "
                            "before enabling assignment by property."
                        ),
                    }
                }
            if team.assign_by_property:
                filtered_member_ids = team._get_filtered_member_ids()
                team.member_ids = [(6, 0, filtered_member_ids)]

    @api.constrains("assign_by_property", "team_job_ids")
    def _check_assign_by_property(self):
        for team in self:
            if team.assign_by_property and not team.team_job_ids:
                raise ValidationError(
                    _(
                        "To use 'Assign based on Hotel and Ticket Type', "
                        "at least one job position must be associated with the team."
                    )
                )

    @api.constrains("assign_by_property", "member_ids")
    def _check_member_ids_modification(self):
        for team in self:
            if team.assign_by_property:
                expected_members = set(team._get_filtered_member_ids())
                current_members = set(team.member_ids.ids)
                if current_members != expected_members:
                    raise ValidationError(
                        _(
                            "You cannot manually modify team members when "
                            "'Assign by Property' is active. "
                            "Members are automatically assigned based on jobs and properties. "
                        )
                    )

    def _determine_user_to_assign(self, ticket=None, vals=None):
        result = dict.fromkeys(self.ids, self.env["res.users"])

        context = self.env.context
        no_property_assignment = context.get("no_property_assignment", False)
        no_property_vals = vals.get("pms_property_id", False) if vals else False
        default_tickets_with_property = context.get(
            "default_tickets_with_property", False
        )

        if no_property_assignment and (
            no_property_vals or not default_tickets_with_property
        ):
            result = super()._determine_user_to_assign()
            return result

        if default_tickets_with_property:
            if ticket:
                team_id = ticket.team_id.id
            elif vals:
                team_id = vals.get("team_id")
            elif hasattr(self, "team_id") and self.team_id:
                team_id = self.team_id.id
            else:
                team_id = False

            team = self.env["helpdesk.team"].browse(team_id) if team_id else self
            teams_to_process = (
                team
                if team.assign_method in ["randomly", "balanced"]
                and team.auto_assignment
                else self.env["helpdesk.team"]
            )

            if teams_to_process:
                for team in teams_to_process:
                    if not team.member_ids:
                        continue

                    members = team._get_members_from_jobs(ticket=ticket, vals=vals)
                    member_ids = members.ids

                    if not member_ids:
                        result[team.id] = self.env["res.users"]
                        continue

                    if team.assign_method == "randomly":
                        last_ticket_user = (
                            self.env["helpdesk.ticket"]
                            .search(
                                [("team_id", "=", team.id), ("user_id", "!=", False)],
                                order="create_date desc, id desc",
                                limit=1,
                            )
                            .user_id
                        )

                        index = 0
                        if last_ticket_user and last_ticket_user.id in member_ids:
                            prev_index = member_ids.index(last_ticket_user.id)
                            index = (prev_index + 1) % len(member_ids)

                        assigned_user = self.env["res.users"].browse(member_ids[index])
                        result[team.id] = assigned_user

                    elif team.assign_method == "balanced":
                        ticket_count_data = self.env["helpdesk.ticket"].read_group(
                            [
                                ("stage_id.fold", "=", False),
                                ("user_id", "in", member_ids),
                                ("team_id", "=", team.id),
                            ],
                            ["user_id"],
                            ["user_id"],
                        )

                        open_ticket_map = dict.fromkeys(member_ids, 0)
                        open_ticket_map.update(
                            {
                                item["user_id"][0]: item["user_id_count"]
                                for item in ticket_count_data
                            }
                        )

                        selected_user_id = min(open_ticket_map, key=open_ticket_map.get)
                        assigned_user = self.env["res.users"].browse(selected_user_id)
                        result[team.id] = assigned_user

        else:
            result = super()._determine_user_to_assign()

        return result
