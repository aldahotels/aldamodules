from odoo import api, fields, models, tools


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _assign_user_based_on_property_type(self, tickets_with_property=False):
        if not tickets_with_property:
            return self

        for ticket in self:
            if ticket.user_id:
                continue

            if not (ticket.team_id and ticket.pms_property_id):
                continue

            vals_for_assignment = {
                "pms_property_id": ticket.pms_property_id.id,
                "ticket_type_id": ticket.ticket_type_id.id,
                "team_id": ticket.team_id.id,
            }

            ctx = {
                "default_tickets_with_property": True,
                "no_property_assignment": False,
            }

            assigned_user = (
                ticket.team_id.with_context(**ctx)
                ._determine_user_to_assign(ticket=ticket, vals=vals_for_assignment)
                .get(ticket.team_id.id)
            )

            if assigned_user:
                ticket.user_id = assigned_user.id

            if not ticket.stage_id or ticket.stage_id not in ticket.team_id.stage_ids:
                stage = ticket.team_id._determine_stage().get(ticket.team_id.id)
                ticket.stage_id = stage

        return self

    @api.depends("team_id", "pms_property_id", "ticket_type_id")
    def _compute_user_and_stage_ids(self):
        for ticket in self:
            if ticket.user_id:
                continue

            if ticket.team_id and ticket.pms_property_id and ticket.ticket_type_id:
                ticket._assign_user_based_on_property_type(
                    tickets_with_property=True,
                )

    @api.model
    def default_get(self, fields):

        result = super(HelpdeskTicket, self).default_get(fields)

        if result.get("team_id") and fields:
            team = self.env["helpdesk.team"].browse(result["team_id"])

            if "stage_id" in fields and "stage_id" not in result:
                result["stage_id"] = team._determine_stage()[team.id].id

        return result

    @api.model_create_multi
    def create(self, list_value):  # noqa: C901
        now = fields.Datetime.now()

        teams = self.env["helpdesk.team"].browse(
            [vals["team_id"] for vals in list_value if vals.get("team_id")]
        )

        teams_with_property_assignment = teams.filtered("assign_by_property")
        teams_without_property_assignment = teams - teams_with_property_assignment

        team_default_map = {}
        for team in teams:
            team_default_map[team.id] = {
                "stage_id": team._determine_stage()[team.id].id,
            }

        if teams_without_property_assignment:
            for team in teams_without_property_assignment:
                team_default_map[team.id]["user_id"] = (
                    team.with_context(no_property_assignment=True)
                    ._determine_user_to_assign()[team.id]
                    .id
                )

        for vals in list_value:
            partner_id = vals.get("partner_id", False)
            partner_name = vals.get("partner_name", False)
            partner_email = vals.get("partner_email", False)

            if partner_name and partner_email and not partner_id:
                parsed_name, parsed_email = self.env["res.partner"]._parse_partner_name(
                    partner_email
                )
                parsed_name = parsed_name or partner_name
                team = (
                    self.env["helpdesk.team"].browse(vals.get("team_id"))
                    if vals.get("team_id")
                    else False
                )
                company = team.company_id.id if team else False

                vals["partner_id"] = (
                    self.env["res.partner"]
                    .with_context(default_company_id=company)
                    .find_or_create(tools.formataddr((parsed_name, parsed_email)))
                    .id
                )

        partner_ids = [
            vals["partner_id"]
            for vals in list_value
            if "partner_id" in vals
            and vals.get("partner_id")
            and "partner_email" not in vals
        ]
        partners = self.env["res.partner"].browse(partner_ids)
        partner_email_map = {partner.id: partner.email for partner in partners}
        partner_name_map = {partner.id: partner.name for partner in partners}
        company_per_team_id = {t.id: t.company_id for t in teams}

        for vals in list_value:
            company = company_per_team_id.get(vals.get("team_id", False))
            # vals['ticket_ref'] = self.env['ir.sequence'].with_company(company).sudo(
            # ).next_by_code('helpdesk.ticket')

            if vals.get("team_id"):
                team_default = team_default_map[vals["team_id"]]

                if "stage_id" not in vals:
                    vals["stage_id"] = team_default["stage_id"]

                if "user_id" not in vals:
                    team_id = vals["team_id"]
                    team = self.env["helpdesk.team"].browse(team_id)

                    if not team.assign_by_property:
                        if (
                            teams_without_property_assignment
                            and team_id in teams_without_property_assignment.ids
                        ):
                            vals["user_id"] = team_default.get("user_id")

                if vals.get("user_id"):
                    vals["assign_date"] = fields.Datetime.now()
                    vals["assign_hours"] = 0

            if vals.get("partner_id") in partner_email_map:
                vals["partner_email"] = partner_email_map.get(vals["partner_id"])
            if vals.get("partner_id") in partner_name_map:
                vals["partner_name"] = partner_name_map.get(vals["partner_id"])

            if vals.get("stage_id"):
                vals["date_last_stage_update"] = now
            vals["oldest_unanswered_customer_message_date"] = now

        tickets = super(HelpdeskTicket, self).create(list_value)

        for ticket in tickets:
            if ticket.partner_id:
                ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
            ticket._portal_ensure_token()

        tickets.sudo()._sla_apply()

        tickets_with_property = tickets.filtered(
            lambda t: t.pms_property_id and t.team_id.assign_by_property
        )

        if tickets_with_property:
            tickets_with_property._assign_user_based_on_property_type(
                tickets_with_property=True
            )
        return tickets
