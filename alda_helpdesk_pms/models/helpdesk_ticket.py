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
        default=False,
        tracking=True,
        help="Indicates if the room is blocked for this ticket.",
    )

    is_room = fields.Boolean(
        string="Room's ticket",
        compute="_compute_is_room",
        store=True,
        default=False,
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

    property_count_tickets = fields.Integer(
        string="Total Tickets",
        compute="_compute_take_ticket_count",
    )

    occupancy_rate = fields.Float(
        string="Occupancy Rate (%)",
        compute="_compute_show_daily_kpi",
        digits=(16, 2),
        default=0.0,
    )

    date_today = fields.Date(
        string="Date",
        default=fields.Date.today(),
        store=False,
    )

    blocked_rooms = fields.Integer(
        string="Total Blocked Rooms",
        compute="_compute_show_daily_kpi",
        store=True,
    )

    ticket_blocked_room_adr_accumulated = fields.Float(
        string="Accumulated ADR (Blocked Room)",
        compute="_compute_blocked_room_adr",
        store=True,
        digits=(16, 2),
    )

    total_days_blocked = fields.Integer(
        string="Accumulated Days (Blocked Room)",
        compute="_compute_blocked_room_adr",
        store=True,
    )

    occupancy_kpi_info = fields.Char(string="Occupancy Rate Info")
    block_kpi_info = fields.Char(string="Out Rate Info")

    alert_level = fields.Selection(
        [
            ("none", "No Alert"),
            ("low", "Low Occupation"),
            ("medium", "Medium Occupation"),
            ("high", "High Occupation"),
            ("critical", "Critical Alert"),
        ],
        compute="_compute_alert_level",
        store=False,
    )

    @api.depends("pms_property_id")
    def _compute_take_ticket_count(self):
        for ticket in self:
            if ticket.pms_property_id:
                property_record = (
                    self.env["pms.property"].sudo().browse(ticket.pms_property_id.id)
                )
                ticket.property_count_tickets = property_record.ticket_count
            else:
                ticket.property_count_tickets = 0

    def action_open_property_tickets(self):
        self.ensure_one()

        if not self.pms_property_id:
            raise ValidationError(_("This ticket is not associated with any property."))

        return self.pms_property_id.action_view_tickets()

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
                ticket.ticket_blocked_room_adr_accumulated = 0.0
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
                ticket.ticket_blocked_room_adr_accumulated = 0.0

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
                "title": "Update done",
                "message": f"{updated_count} tickets has been updated",
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }

    @api.depends("pms_property_id")
    def _compute_show_daily_kpi(self):
        today = fields.Date.today(self)

        for ticket in self:
            if not ticket.pms_property_id:
                ticket.occupancy_rate = 0.0
                ticket.blocked_rooms = 0
                continue

            kpi = self.env["pms.daily.kpi"].create_or_update_daily_kpi(
                ticket.pms_property_id.id,
                today,
            )

            rate = round(kpi.occupancy_rate * 100) if kpi.occupancy_rate else 0

            ticket.update(
                {
                    "occupancy_rate": kpi.occupancy_rate or 0.0,
                    "blocked_rooms": kpi.blocked_rooms or 0,
                    "occupancy_kpi_info": _(
                        "%(rate)s%% Occupancy Rate", rate=int(rate)
                    ),
                    "block_kpi_info": _(
                        "%(count)s Room Out of Service", count=kpi.blocked_rooms or 0
                    ),
                }
            )

    def action_view_kpi_ticket(self):
        self.ensure_one()

        # Obtener o crear el KPI real
        kpi = self.env["pms.daily.kpi"].create_or_update_daily_kpi(
            self.pms_property_id.id, fields.Date.today()
        )

        # Crear el registro transitorio con el KPI asignado
        kpi_show = self.env["pms.daily.kpi.show"].create(
            {
                "kpi_id": kpi.id,
            }
        )

        return {
            "name": "KPIs Diarios",
            "type": "ir.actions.act_window",
            "res_model": "pms.daily.kpi.show",
            "view_mode": "form",
            "target": "new",
            "res_id": kpi_show.id,
            "view_id": self.env.ref("alda_pms_kpi.pms_daily_kpi_show_ticket_form").id,
            "context": {
                "form_view_initial_mode": "readonly",
                "create": False,
                "edit": False,
                "delete": False,
                "flags": {
                    "action_buttons": False,
                    "sidebar": False,
                    "create": False,
                    "edit": False,
                    "delete": False,
                },
            },
        }

    # def action_view_kpi_ticket(self):
    #     self.ensure_one()
    #     return {
    #         'name': 'KPIs Diarios',
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'pms.daily.kpi.show',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': {
    #             'default_pms_property_id': self.pms_property_id.id or False,
    #             'default_date_today': fields.Date.today(),
    #         },
    #         'view_id': self.env.ref('alda_pms_kpi.pms_daily_kpi_show_ticket_form').id,
    #     }

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

    @api.depends("pms_room_id", "is_room_blocked")
    def _compute_blocked_room_adr(self):
        for ticket in self:
            ticket.ticket_blocked_room_adr_accumulated = 0.0

            if not (
                ticket.pms_property_id
                and ticket.is_room_blocked
                and ticket.create_date
                and not ticket.close_date
            ):
                continue

            room = ticket.pms_room_id
            room_type = room.room_type_id if room else False
            if not room_type:
                continue
            start_date = ticket.create_date.date()
            end_date = (
                ticket.close_date.date()
                if ticket.close_date
                else fields.Date.today(ticket)
            )
            blocked_line = (
                self.env["pms.reservation.line"]
                .sudo()
                .search(
                    [
                        ("room_id", "=", room.id),
                        ("reservation_id.reservation_type", "=", "out"),
                        ("state", "not in", ["draft", "cancel"]),
                        ("date", ">=", start_date),
                        ("date", "<=", end_date),
                    ],
                    order="date ASC",
                )
            )

            if not blocked_line:
                continue

            room_type_price = room_type.list_price or 0.0

            total_days = (end_date - start_date).days
            total_days_room_blocked = len(blocked_line) if blocked_line else total_days
            total_days = 1 if total_days == 0 else total_days
            if total_days < 0:
                total_days = 1

            adr_total_blocked = room_type_price * total_days_room_blocked

            ticket.ticket_blocked_room_adr_accumulated = adr_total_blocked
            ticket.total_days_blocked = total_days_room_blocked

    @api.depends(
        "pms_property_id", "is_room_blocked", "total_days_blocked", "occupancy_rate"
    )
    def _compute_alert_level(self):
        for ticket in self:
            if not ticket.pms_property_id or not ticket.is_room_blocked:
                ticket.alert_level = "none"
                continue

            days = ticket.total_days_blocked or 0
            occ = ticket.occupancy_rate or 0.0

            if occ == 0.0 or not ticket.is_room_blocked:
                ticket.alert_level = "none"
            elif occ <= 0.30 and days <= 15:
                ticket.alert_level = "low"
            elif (0.30 < occ <= 0.70 and days <= 30) or (days > 15 and occ <= 0.70):
                ticket.alert_level = "medium"
            elif occ > 0.70 and days <= 30:
                ticket.alert_level = "high"
            elif occ > 0.70 and days > 30:
                ticket.alert_level = "critical"
            else:
                ticket.alert_level = "none"
