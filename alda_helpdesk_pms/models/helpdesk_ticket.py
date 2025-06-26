from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessDenied
import json
import os


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    ticket_type_id = fields.Many2one(
        comodel_name="helpdesk.ticket.type",
        tracking=True,
        domain="[('team_id', '=', team_id)]",
        help="The type of ticket, which determines its specific characteristics and workflow.",
    )

    pms_room_blocked = fields.Boolean(
        compute="_compute_pms_room_blocked",
        store=True,
        help="Indicates if the room is blocked for this ticket.",
    )

    is_room = fields.Boolean(
        compute="_compute_is_room",
        store=True,
        help="Indicates if the ticket is related to a room.",
    )

    bathroom_type = fields.Selection(
        selection=[("bathroom", "Bathroom"), ("none", "None")],
        help="Select if it's specifically the bathroom.",
        store=True,
        default="none",
        traking=True,
    )

    company_external_id = fields.Boolean(
        string="Repair External ID",
        default=False,
        store=True,
        tracking=True,
        help="Indicates if the ticket is linked to an external repair ID.",
    )

    def _get_location_selection(self):
        file_path = os.path.join(
            os.path.dirname(__file__), "../data/location_data.json"
        )

        try:
            with open(file_path, "r") as f:
                location_data = json.load(f)
            selection = []
            for category in location_data.values():
                for key, value in category.items():
                    selection.append((key, value))

            return selection
        except Exception:
            return [
                ("bathroom", "Bathroom"),
                ("room", "Room"),
                ("reception", "Reception"),
            ]

    location_type = fields.Selection(
        selection=_get_location_selection,
        string="Location type",
        help="Select where this issue is located",
        default="room",
    )

    def _is_room_blocked(self, room_id):
        reservation = (
            self.env["pms.reservation"]
            .sudo()
            .search(
                [
                    ("reservation_type", "in", ["out"]),
                    ("reservation_line_ids.room_id", "=", room_id),
                    ("reservation_line_ids.date", "=", fields.Date.today()),
                    ("reservation_line_ids.state", "=", "confirm"),
                ],
                limit=1,
            )
        )
        return bool(reservation)

    @api.depends("pms_room_id")
    def _compute_pms_room_blocked(self):
        for ticket in self:
            ticket.pms_room_blocked = (
                self._is_room_blocked(ticket.pms_room_id.id)
                if ticket.pms_room_id
                else False
            )

    @api.onchange("team_id")
    def _onchange_team_id_update_ticket_type_domain(self):
        result = {}
        if self.team_id:
            result["domain"] = {"ticket_type_id": [("team_id", "=", self.team_id.id)]}
        else:
            result["domain"] = {"ticket_type_id": []}
        return result

    @api.depends("pms_room_id")
    def _compute_is_room(self):
        for ticket in self:
            if ticket.is_room != bool(ticket.pms_room_id):
                ticket.is_room = bool(ticket.pms_room_id)
                if ticket.is_room:
                    ticket.location_type = False
                if ticket.id:
                    msg = "Related to:" if ticket.is_room else "Unrelated to:"
                    ticket.message_post(
                        body=(
                            f"{msg}</b> Room -> {ticket.pms_room_id.name} | "
                            f"Property -> {ticket.pms_property_id.name}"
                        ),
                        subject=_("Room status changed"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                        content_subtype="html",
                    )
            else:
                if ticket.id:
                    msg = "Unrelated to:" if not ticket.is_room else ""
                    ticket.message_post(
                        body=(
                            f"{msg}</b> Not room in ticket -> "
                            f"Property: {ticket.pms_property_id.name}"
                        ),
                        subject=_("Room status changed"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                        content_subtype="html",
                    )

    @api.onchange("pms_room_id")
    def _onchange_pms_room_id(self):
        pass

    @api.constrains("location_type", "pms_room_id", "bathroom_type")
    def _check_room_location_consistency(self):
        for ticket in self:
            if ticket.location_type == "room" and not ticket.pms_room_id:
                raise ValidationError(
                    _("Room is required when location type is 'Room'")
                )
            if ticket.location_type == "bathroom" and (
                not ticket.pms_room_id or not ticket.bathroom_type
            ):
                raise ValidationError(
                    _(
                        "Both Room and Bathroom selection are required "
                        "when location type is 'Bathroom'"
                    )
                )