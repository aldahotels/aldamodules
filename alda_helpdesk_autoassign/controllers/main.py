import logging

from odoo.http import request

from odoo.addons.alda_helpdesk_pms.controllers.main import HelpdeskFormController

_logger = logging.getLogger(__name__)


class HelpdeskFormControllerInherit(HelpdeskFormController):
    def _prepare_ticket_vals(self, post):
        vals = super()._prepare_ticket_vals(post)

        team_id = vals.get("team_id")
        if not team_id:
            return vals

        team = request.env["helpdesk.team"].sudo().browse(team_id)
        if not team.assign_by_property:
            return vals

        if vals.get("user_id"):
            return vals

        pms_property_id = vals.get("pms_property_id")
        ticket_type_id = vals.get("ticket_type_id")

        if isinstance(ticket_type_id, str):
            try:
                ticket_type_id = int(ticket_type_id)
                vals["ticket_type_id"] = ticket_type_id
            except ValueError:
                ticket_type_id = None

        if isinstance(pms_property_id, str):
            try:
                pms_property_id = int(pms_property_id)
            except ValueError:
                pms_property_id = None

        if team_id and pms_property_id and ticket_type_id:

            ctx = {
                "default_pms_property_id": pms_property_id,
                "default_ticket_type_id": ticket_type_id,
                "default_tickets_with_property": True,
            }

            assigned_user = (
                team.with_context(**ctx)
                ._determine_user_to_assign(vals=vals)
                .get(team.id)
            )

            if assigned_user:
                vals["user_id"] = assigned_user.id

        return vals
