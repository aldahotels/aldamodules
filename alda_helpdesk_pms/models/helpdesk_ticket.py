import json
import logging
import os
from datetime import timedelta
from random import randint

from dateutil.easter import easter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HelpdeskPmsTicketDetailsTag(models.Model):
    _name = "helpdesk.ticket.detail.tag"
    _description = "Helpdesk PMS Ticket Details"
    _order = "name"
    _log_access = False
    _auto = True
    _transient = False

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(required=True, translate=True)
    tag_key = fields.Char(required=True, unique=True)
    color = fields.Integer(default=_get_default_color)


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _get_tag_translations(self):
        return {
            "is_room": {"name": _("Room"), "color": 3},
            "is_blocked_room": {"name": _("Blocked Room"), "color": 9},
            "is_bathroom": {"name": _("Bathroom"), "color": 11},
            "external_company": {"name": _("External Company"), "color": 10},
        }

    ticket_type_id = fields.Many2one(
        comodel_name="helpdesk.ticket.type",
        tracking=True,
        domain="[('team_id', '=', team_id)]",
        help="The type of ticket, which determines its specific characteristics and workflow.",
    )

    tag_detail = fields.Many2many(
        comodel_name="helpdesk.ticket.detail.tag",
        relation="helpdesk_ticket_helpdesk_ticket_detail_tag_rel",
        column1="ticket_id",
        column2="detail_tag_id",
        string="Tag Details",
        compute="_compute_tag_detail",
        tracking=True,
        store=True,
    )

    is_room_blocked = fields.Boolean(
        string="Blocked",
        compute="_compute_is_room_blocked",
        store=True,
        tracking=True,
        help="Indicates if the room is blocked for this ticket.",
    )

    is_room = fields.Boolean(
        string="Room's ticket",
        compute="_compute_is_room",
        store=True,
        help="Indicates if the ticket is related to a room.",
    )

    is_bathroom = fields.Boolean(
        string="Bathroom's room",
        compute="_compute_is_bathroom",
        store=True,
        help="Indicates if the ticket is related to a bathroom.",
    )

    company_external_id = fields.Boolean(
        string="Repair External ID",
        default=False,
        store=True,
        tracking=True,
        help="Indicates if the ticket is linked to an external repair ID.",
    )

    season_type = fields.Selection(
        [
            ("high", "High Season"),
            ("low", "Low Season"),
        ],
        string="Season",
        compute="_compute_season_type",
        store=False,
    )

    def _compute_season_type(self):
        for ticket in self:
            if not ticket.create_date:
                ticket.season_type = False
                continue
            create_date = fields.Date.from_string(ticket.create_date.date())
            year = ticket.create_date.year
            easter_date = easter(year)
            palm_sunday = easter_date - timedelta(days=7)
            holy_start = palm_sunday - timedelta(days=4)
            holy_end = easter_date + timedelta(days=4)

            is_holy_period = holy_start <= create_date <= holy_end

            month = create_date.month

            if 6 <= month <= 9:
                ticket.season_type = "high"
            elif is_holy_period:
                ticket.season_type = "high"
            elif month == 12 or (month == 1 and ticket.create_date.day <= 7):
                ticket.season_type = "high"
            else:
                ticket.season_type = "low"

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
                ("bathroom", _("Bathroom")),
                ("room", _("Room")),
                ("reception", _("Reception")),
            ]

    location_type = fields.Selection(
        selection=_get_location_selection,
        string="Location type",
        help="Select where this issue is located",
        store=True,
    )

    def _is_room_blocked(self, pms_room_id):
        today = fields.Date.context_today(self)
        line = (
            self.env["pms.reservation.line"]
            .sudo()
            .search(
                [
                    ("room_id", "=", pms_room_id.id),
                    ("date", "=", today),
                    ("overnight_room", "=", True),
                    ("reservation_id.state", "not in", ["draft", "cancel"]),
                    ("reservation_id.reservation_type", "=", "out"),
                ],
                limit=1,
            )
        )
        return bool(line)

    @api.depends("pms_room_id")
    def _compute_is_room_blocked(self):
        for ticket in self:
            if not ticket.pms_room_id:
                ticket.is_room_blocked = False
                ticket.color = 0
            else:
                ticket.is_room_blocked = self._is_room_blocked(ticket.pms_room_id)
                ticket.color = 9 if ticket.is_room_blocked else 0

    @api.onchange("team_id")
    def _onchange_team_id_update_ticket_type_domain(self):
        result = {}
        for ticket in self:
            if ticket.team_id:
                result["domain"] = {
                    "ticket_type_id": [("team_id", "=", ticket.team_id.id)]
                }
            else:
                result["domain"] = {"ticket_type_id": []}
            return result

    @api.depends("pms_room_id", "location_type")
    def _compute_is_room(self):
        for ticket in self:
            previous_is_room = ticket.is_room
            current_is_room = bool(ticket.pms_room_id)
            ticket.is_room = current_is_room

            if current_is_room and ticket.location_type != "bathroom":
                ticket.location_type = "room"

            if ticket.id and previous_is_room != current_is_room:
                msg = (
                    _("Related to Room")
                    if current_is_room
                    else _("No longer related to Room")
                )
                room_name = ticket.pms_room_id.name if ticket.pms_room_id else _("N/A")
                property_name = ticket.pms_property_id.name or _("N/A")
                ticket.message_post(
                    body=f"{msg}: {room_name} | Property: {property_name}",
                    subject=_("Room status changed"),
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                    content_subtype="html",
                )

    @api.depends("location_type")
    def _compute_is_bathroom(self):
        for ticket in self:
            ticket.is_bathroom = ticket.location_type == "bathroom"

    @api.onchange("location_type")
    def _onchange_location_type_clear_room(self):
        for ticket in self:
            if ticket.location_type not in ["room", "bathroom"]:
                ticket.pms_room_id = False
                ticket.is_bathroom = False
                ticket.is_room = False
                ticket.is_room_blocked = False

    @api.constrains("location_type", "pms_room_id")
    def _check_location_consistency(self):
        for ticket in self:
            if ticket.location_type == "room" and not ticket.pms_room_id:
                raise ValidationError(
                    _("Room is required when location type is 'Room'")
                )

            if ticket.location_type == "bathroom":
                if not ticket.pms_room_id:
                    raise ValidationError(
                        _("Room is required when location type is 'Bathroom'")
                    )

    @api.constrains("team_id", "ticket_type_id")
    def _check_team_ticket_type(self):
        for ticket in self:
            if (
                ticket.ticket_type_id
                and ticket.ticket_type_id.team_id != ticket.team_id
            ):
                raise ValidationError(
                    _(
                        "The selected ticket type doesn't belong to the current team. "
                        "Please select a type that corresponds to the selected team."
                    )
                )

    @api.onchange("team_id")
    def _onchange_team_id(self):
        """Clear ticket type when team changes if they don't match"""
        if self.ticket_type_id and self.ticket_type_id.team_id != self.team_id:
            self.ticket_type_id = False

    def _prepare_tag_detail_pms(self, tag_key, tag_ids):
        tag = self.env["helpdesk.ticket.detail.tag"].search(
            [("tag_key", "=", tag_key)], limit=1
        )
        if not tag:
            tag_data = self._get_tag_translations()[tag_key]
            tag = self.env["helpdesk.ticket.detail.tag"].create(
                {
                    "name": tag_data["name"],
                    "tag_key": tag_key,
                    "color": tag_data["color"],
                }
            )
        tag_ids.append(tag.id)
        return tag_ids

    @api.depends("is_room", "is_room_blocked", "is_bathroom", "company_external_id")
    def _compute_tag_detail(self):
        for ticket in self:
            try:
                tag_ids = []
                if ticket.is_room:
                    self._prepare_tag_detail_pms("is_room", tag_ids)
                if ticket.is_room_blocked:
                    self._prepare_tag_detail_pms("is_blocked_room", tag_ids)
                if ticket.is_bathroom:
                    self._prepare_tag_detail_pms("is_bathroom", tag_ids)
                if ticket.company_external_id:
                    self._prepare_tag_detail_pms("external_company", tag_ids)

                ticket.tag_detail = [(6, 0, tag_ids)] if tag_ids else False

            except Exception as e:
                _logger.error(
                    "Error al calcular tags del ticket %s: %s", ticket.id, str(e)
                )
                ticket.tag_detail = False

    def action_update_is_room_blocked(self):
        tickets = self.search([("pms_room_id", "!=", False)])
        updated_count = 0

        for ticket in tickets:
            is_blocked = self._is_room_blocked(ticket.pms_room_id)
            if ticket.is_room_blocked != is_blocked:
                ticket.write(
                    {"is_room_blocked": is_blocked, "color": 9 if is_blocked else 0}
                )
                updated_count += 1

        self.env["helpdesk.ticket"].search([])._compute_is_room_blocked()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Actualización completada",
                "message": f"{updated_count} tickets actualizados",
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }
