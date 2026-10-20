from datetime import datetime, timedelta

import pytz

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.pms_ai_tool.tools import guarded_tool

from .lab import lab_silence

MAX_NIGHTS = 14
MAX_ROOMS = 40
# Smart lock codes are generated for check-ins within 24 hours.
MIN_DAYS_AHEAD = 2
NO_BOARD = "NONE"
LAB_MARK = "[LAB]"
PARAM_SALE_CHANNEL = "alda_ai_lab.group_sale_channel_id"

GROUP_INPUT = {
    "property_id": {"type": "integer", "description": "Hotel (pms.property id)."},
    "checkin": {"type": "string", "format": "date"},
    "checkout": {"type": "string", "format": "date"},
    "rooms": {
        "type": "array",
        "minItems": 1,
        "maxItems": 6,
        "items": {
            "type": "string",
            "maxLength": 24,
            "pattern": r"[A-Za-z0-9._-]{1,16}=[1-9][0-9]{0,2}",
        },
        "description": "Room type code and number of rooms, for example DBL=20.",
    },
    "adults": {
        "type": "integer",
        "minimum": 1,
        "maximum": 6,
        "description": "Adults per room.",
    },
    "children": {"type": "integer", "minimum": 0, "maximum": 4},
    "board_service_code": {
        "type": "string",
        "maxLength": 16,
        "description": "Board code (for example MP or AD), or %s for room "
        "only. Default: the default board of each room type." % NO_BOARD,
    },
    "pricelist_id": {"type": "integer"},
    "partner_id": {
        "type": "integer",
        "description": "Customer company of the group.",
    },
    "partner_name": {
        "type": "string",
        "maxLength": 120,
        "description": "Name of the group holder when there is no partner_id: a "
        "company with exactly this name is used if there is one.",
    },
    "sale_channel_id": {"type": "integer"},
    "group_name": {"type": "string", "maxLength": 100},
    "preconfirm": {
        "type": "boolean",
        "description": "True confirms the reservations; false (default) leaves "
        "them as pre-reservations, which still hold the rooms.",
    },
}


class AldaAiLabGroupTools(models.AbstractModel):
    _name = "alda.ai.lab.group.tools"
    _inherit = "alda.ai.lab.mixin"
    _description = "AI lab tools: group bookings"

    # Checks of the request

    @api.model
    def _lab_group_property(self, property_id):
        self.env["pms.ai.tools"]._ai_scope_property_ids([property_id])
        prop = self.env["pms.property"].browse(property_id)
        return prop.with_company(prop.company_id)

    @api.model
    def _lab_group_dates(self, prop, checkin, checkout):
        tz = pytz.timezone(prop.tz or self.env.user.tz or "Europe/Madrid")
        today = datetime.now(tz).date()
        if checkin < today + timedelta(days=MIN_DAYS_AHEAD):
            raise UserError(
                _("A lab group must arrive in %s days or later.") % MIN_DAYS_AHEAD
            )
        nights = (checkout - checkin).days
        if nights < 1:
            raise UserError(_("The checkout must be after the checkin."))
        if nights > MAX_NIGHTS:
            raise UserError(_("A lab group stays %s nights at most.") % MAX_NIGHTS)
        return [checkin + timedelta(days=offset) for offset in range(nights)]

    @api.model
    def _lab_group_partner(self, prop, partner_id, partner_name, warnings):
        Partner = self.env["res.partner"]
        anonymous = self.env.ref("pms.various_pms_partner", raise_if_not_found=False)
        if partner_id:
            partner = Partner.browse(partner_id).exists()
            if not partner:
                raise UserError(_("There is no partner %s.") % partner_id)
        elif partner_name:
            partner = Partner.search(
                [
                    ("is_company", "=", True),
                    ("name", "=ilike", partner_name),
                    "|",
                    ("pms_property_ids", "=", False),
                    ("pms_property_ids", "in", prop.ids),
                ],
                limit=2,
            )
            if len(partner) != 1:
                candidates = Partner.search(
                    [("is_company", "=", True), ("name", "ilike", partner_name)],
                    limit=5,
                )
                if candidates:
                    warnings.append(
                        _(
                            "No single company called %(name)s: the folio only "
                            "carries the name. Similar: %(similar)s."
                        )
                        % {
                            "name": partner_name,
                            "similar": ", ".join(
                                f"{c.name} ({c.id})" for c in candidates
                            ),
                        }
                    )
                partner = Partner
        else:
            raise UserError(_("Say who the group is for: partner_id or partner_name."))
        if partner and (partner == anonymous or partner.is_agency):
            raise UserError(
                _("%s cannot hold a group: pick the customer company.")
                % partner.display_name
            )
        if (
            partner
            and partner.pms_property_ids
            and prop not in partner.pms_property_ids
        ):
            raise UserError(
                _("The partner %s does not belong to this hotel.") % partner.name
            )
        return partner

    @api.model
    def _lab_group_pricelist(self, prop, partner, pricelist_id):
        if pricelist_id:
            pricelist = self.env["product.pricelist"].browse(pricelist_id).exists()
        elif partner and partner.property_product_pricelist.is_pms_available:
            pricelist = partner.property_product_pricelist
        else:
            pricelist = prop.default_pricelist_id
        if not pricelist or not pricelist.is_pms_available:
            raise UserError(_("The pricelist is not one of the PMS."))
        if pricelist.pms_property_ids and prop not in pricelist.pms_property_ids:
            raise UserError(
                _("The pricelist %s is not for this hotel.") % pricelist.name
            )
        if pricelist.discount_policy != "with_discount":
            # The night prices of the PMS fail with the other policy.
            raise UserError(
                _("The pricelist %s does not include discounts in the price.")
                % pricelist.name
            )
        return pricelist

    @api.model
    def _lab_group_channel(self, prop, sale_channel_id):
        Channel = self.env["pms.sale.channel"]
        if not sale_channel_id:
            param = self.env["ir.config_parameter"].sudo().get_param(PARAM_SALE_CHANNEL)
            sale_channel_id = int(param) if param and param.isdigit() else None
        domain = [
            ("channel_type", "=", "direct"),
            "|",
            ("pms_property_ids", "=", False),
            ("pms_property_ids", "in", prop.ids),
        ]
        channels = Channel.search(domain)
        if sale_channel_id:
            channel = channels.filtered(lambda c: c.id == sale_channel_id)
            if not channel:
                raise UserError(
                    _("The sale channel %s is not a direct channel of this hotel.")
                    % sale_channel_id
                )
            return channel
        if len(channels) != 1:
            raise UserError(
                _("Choose the sale channel (sale_channel_id): %s.")
                % ", ".join(f"{c.name} ({c.id})" for c in channels)
            )
        return channels

    @api.model
    def _lab_group_room_types(self, prop, rooms):
        catalog = {
            (room_type.default_code or "").upper(): room_type
            for room_type in prop.room_ids.room_type_id
            if room_type.overnight_room
        }
        requested = {}
        for item in rooms:
            code, count = item.split("=")
            room_type = catalog.get(code.upper())
            if not room_type:
                known = []
                for known_code, known_type in sorted(catalog.items()):
                    count_rooms = len(
                        prop.room_ids.filtered(
                            lambda room, rt=known_type: room.room_type_id == rt
                        )
                    )
                    known.append(f"{known_code} ({known_type.name}, {count_rooms})")
                raise UserError(
                    _("Unknown room type %(code)s. The hotel has: %(types)s.")
                    % {"code": code, "types": ", ".join(known)}
                )
            requested[room_type] = requested.get(room_type, 0) + int(count)
        if sum(requested.values()) > MAX_ROOMS:
            raise UserError(_("A lab group has %s rooms at most.") % MAX_ROOMS)
        return requested

    @api.model
    def _lab_group_board(self, prop, room_type, code, pricelist, blocking, warnings):
        BoardRoomType = self.env["pms.board.service.room.type"]
        if code and code.upper() == NO_BOARD:
            return BoardRoomType
        if not code:
            default = room_type.get_default_board_service(
                prop.id, room_type.id, pricelist.id
            )
            return (default or BoardRoomType)[:1]
        boards = BoardRoomType.search(
            [
                ("pms_room_type_id", "=", room_type.id),
                ("pms_board_service_id.default_code", "=ilike", code),
                ("pms_property_id", "in", [prop.id, False]),
            ]
        ).sorted(lambda board: not board.pms_property_id)
        board = boards[:1]
        if not board:
            codes = BoardRoomType.search(
                [
                    ("pms_room_type_id", "=", room_type.id),
                    ("pms_property_id", "in", [prop.id, False]),
                ]
            ).mapped("pms_board_service_id.default_code")
            blocking.append(
                _("%(type)s has no board %(code)s here (it has: %(codes)s).")
                % {
                    "type": room_type.default_code,
                    "code": code,
                    "codes": ", ".join(sorted(filter(None, codes))) or "-",
                }
            )
            return board
        if not board.board_service_line_ids.filtered("adults"):
            blocking.append(
                _("The board %(code)s of %(type)s charges nothing to adults.")
                % {"code": code, "type": room_type.default_code}
            )
        if board.pricelist_ids and pricelist not in board.pricelist_ids:
            warnings.append(
                _("The board %(code)s is not meant for the pricelist %(pricelist)s.")
                % {"code": code, "pricelist": pricelist.name}
            )
        return board

    # Availability and prices, read only

    @api.model
    def _lab_group_free_rooms(self, prop, room_type, nights, adults):
        checkin, checkout = nights[0], nights[-1] + timedelta(days=1)
        base = prop.with_context(room_type_id=room_type.id, real_avail=True)
        by_night = {
            str(night): len(
                base.with_context(
                    checkin=night, checkout=night + timedelta(days=1)
                ).free_room_ids
            )
            for night in nights
        }
        # The order of the automatic assignment, plus the capacity it ignores.
        whole_stay = base.with_context(
            checkin=checkin, checkout=checkout, capacity=adults
        ).free_room_ids.sorted(lambda r: (r.assignment_sequence, r.sequence, r.id))
        return by_night, whole_stay

    @api.model
    def _lab_group_plan_warnings(self, prop, room_type, pricelist, nights):
        checkin, checkout = nights[0], nights[-1] + timedelta(days=1)
        if not pricelist.availability_plan_id:
            return []
        rules = self.env["pms.availability.plan.rule"].search(
            [
                ("availability_plan_id", "=", pricelist.availability_plan_id.id),
                ("pms_property_id", "=", prop.id),
                ("room_type_id", "=", room_type.id),
                ("date", ">=", checkin),
                ("date", "<=", checkout),
            ]
        )
        Plan = self.env["pms.availability.plan"]
        warnings = []
        for rule in rules:
            if not Plan.any_rule_applies(checkin, checkout, rule):
                continue
            reasons = [
                label
                for flag, label in (
                    (rule.closed, _("closed")),
                    (rule.closed_arrival, _("closed to arrival")),
                    (rule.closed_departure, _("closed to departure")),
                    (rule.min_stay, _("minimum stay %s") % rule.min_stay),
                    (rule.max_stay, _("maximum stay %s") % rule.max_stay),
                    (rule.quota == 0, _("quota 0")),
                    (rule.max_avail == 0, _("no availability for sale")),
                )
                if flag
            ]
            warnings.append(
                _("%(type)s on %(day)s: %(reasons)s in the sales plan.")
                % {
                    "type": room_type.default_code,
                    "day": rule.date,
                    "reasons": ", ".join(reasons),
                }
            )
        return warnings

    @api.model
    def _lab_group_room_price(self, prop, room_type, pricelist, partner, fpos, nights):
        company, product = prop.company_id, room_type.product_id
        Tax = self.env["account.tax"]
        taxes = fpos.map_tax(
            product.taxes_id.filtered(lambda t: t.company_id == company)
        )
        product = product.with_context(property=prop.id)
        total, fallback = 0.0, []
        for night in nights:
            price, rule_id = pricelist._get_product_price_rule(
                product,
                1.0,
                partner=partner.id or False,
                consumption_date=night,
                pms_property_id=prop.id,
            )
            if not rule_id:
                fallback.append(str(night))
            unit = Tax._fix_tax_included_price_company(
                price, product.taxes_id, taxes, company
            )
            total += taxes.compute_all(unit, pricelist.currency_id, 1, product=product)[
                "total_included"
            ]
        return total, fallback

    @api.model
    def _lab_group_board_price(
        self, prop, board, pricelist, partner, fpos, nights, adults, children
    ):
        """Mirror of how the PMS prices the services of a board."""
        company, currency = prop.company_id, pricelist.currency_id
        Tax = self.env["account.tax"]
        checkin, checkout = nights[0], nights[-1] + timedelta(days=1)
        total = 0.0
        for line in board.board_service_line_ids:
            if not ((adults and line.adults) or (children and line.children)):
                continue
            product = line.product_id
            if product.per_day and product.consumed_on in ("before", "after"):
                shift = 1 if product.consumed_on == "after" else 0
                dates = [night + timedelta(days=shift) for night in nights]
                quantity = (
                    (adults if line.adults else 0) + (children if line.children else 0)
                    if product.per_person
                    else 1
                )
            else:
                dates = [checkin if product.consumed_on == "checkin" else checkout]
                quantity = 1
            taxes = fpos.map_tax(
                product.taxes_id.filtered(lambda t: t.company_id == company)
            )
            for day in dates:
                price = pricelist._get_product_price(
                    product.with_context(
                        board_service_line_id=line.id,
                        property=prop.id,
                        consumption_date=day,
                    ),
                    1.0,
                    partner=partner.id or False,
                    consumption_date=day,
                    pms_property_id=prop.id,
                    board_service_line_id=line.id,
                )
                unit = Tax._fix_tax_included_price_company(
                    price, product.taxes_id, taxes, company
                )
                total += taxes.compute_all(unit, currency, quantity, product=product)[
                    "total_included"
                ]
        return total

    # Tool

    @guarded_tool(
        input_schema=GROUP_INPUT,
        output_schema={
            "can_create": {"type": "boolean"},
            "blocking": {"type": "array", "items": {"type": "string"}},
            "hotel": {"type": "string"},
            "stay": {"type": "object"},
            "holder": {"type": "object"},
            "room_types": {"type": "array", "items": {"type": "object"}},
            "estimated_total": {"type": "number"},
            "state": {"type": "string"},
        },
        required_inputs=["property_id", "checkin", "checkout", "rooms", "adults"],
        write=True,
        apply="_ai_lab_group_booking_create_apply",
        timeout_ms=60000,
    )
    def _ai_lab_group_booking_create(
        self,
        property_id,
        checkin,
        checkout,
        rooms,
        adults,
        children=0,
        board_service_code=None,
        pricelist_id=None,
        partner_id=None,
        partner_name=None,
        sale_channel_id=None,
        group_name=None,
        preconfirm=False,
    ):
        self._lab_check()
        prop = self._lab_group_property(property_id)
        tools = self.with_company(prop.company_id)
        nights = tools._lab_group_dates(prop, checkin, checkout)
        warnings, blocking, lines, reservations = [], [], [], []
        partner = tools._lab_group_partner(prop, partner_id, partner_name, warnings)
        pricelist = tools._lab_group_pricelist(prop, partner, pricelist_id)
        channel = tools._lab_group_channel(prop, sale_channel_id)
        fpos = tools.env["account.fiscal.position"]
        if partner:
            fpos = fpos._get_fiscal_position(partner)
        currency = pricelist.currency_id
        for room_type, count in tools._lab_group_room_types(prop, rooms).items():
            board = tools._lab_group_board(
                prop, room_type, board_service_code, pricelist, blocking, warnings
            )
            by_night, whole_stay = tools._lab_group_free_rooms(
                prop, room_type, nights, adults
            )
            if len(whole_stay) < count:
                blocking.append(
                    _(
                        "%(type)s: %(free)s rooms free for every night for %(adults)s "
                        "adults, %(asked)s asked (free per night: %(nights)s)."
                    )
                    % {
                        "type": room_type.default_code,
                        "free": len(whole_stay),
                        "adults": adults,
                        "asked": count,
                        "nights": ", ".join(f"{d} {n}" for d, n in by_night.items()),
                    }
                )
            warnings += tools._lab_group_plan_warnings(
                prop, room_type, pricelist, nights
            )
            room_price, fallback = tools._lab_group_room_price(
                prop, room_type, pricelist, partner, fpos, nights
            )
            if fallback:
                warnings.append(
                    _(
                        "%(type)s has no price in %(pricelist)s on %(days)s: the "
                        "list price of the room type is used."
                    )
                    % {
                        "type": room_type.default_code,
                        "pricelist": pricelist.name,
                        "days": ", ".join(fallback),
                    }
                )
            board_price = tools._lab_group_board_price(
                prop, board, pricelist, partner, fpos, nights, adults, children
            )
            per_room = currency.round(room_price + board_price)
            chosen = whole_stay[:count]
            lines.append(
                {
                    "code": room_type.default_code,
                    "room_type": room_type.name,
                    "requested": count,
                    "free_by_night": by_night,
                    "free_whole_stay": len(whole_stay),
                    "rooms": chosen.mapped("name"),
                    "board": board.pms_board_service_id.default_code or None,
                    "price_per_room": {
                        "room": currency.round(room_price),
                        "board": currency.round(board_price),
                        "total": per_room,
                    },
                    "subtotal": currency.round(per_room * count),
                }
            )
            reservations += [
                {
                    "room_type_id": room_type.id,
                    "preferred_room_id": room.id,
                    "checkin": checkin,
                    "checkout": checkout,
                    "adults": adults,
                    "children": children,
                    "pricelist_id": pricelist.id,
                    # Always explicit: omitted, the PMS adds the default board.
                    "board_service_room_id": board.id or False,
                    "preconfirm": bool(preconfirm),
                    "reservation_type": "normal",
                }
                for room in chosen
            ]
        total = currency.round(sum(line["subtotal"] for line in lines))
        folio = {
            "pms_property_id": prop.id,
            "pricelist_id": pricelist.id,
            "sale_channel_origin_id": channel.id,
            "reservation_type": "normal",
            "internal_comment": " ".join(
                filter(None, (LAB_MARK, group_name, _("(created by the AI lab)")))
            ),
        }
        if partner:
            folio["partner_id"] = partner.id
        else:
            folio["partner_name"] = partner_name
        holder = {
            "partner_id": partner.id or None,
            "name": partner.name if partner else partner_name,
        }
        result = {
            "can_create": not blocking,
            "blocking": blocking,
            "hotel": prop.name,
            "stay": {
                "checkin": checkin,
                "checkout": checkout,
                "nights": len(nights),
                "adults_per_room": adults,
                "children_per_room": children,
            },
            "holder": holder,
            "pricelist": pricelist.name,
            "sale_channel": channel.name,
            "room_types": lines,
            "estimated_total": total,
            "state": "confirm" if preconfirm else "draft",
        }
        if blocking:
            summary = _("The group cannot be created: %s") % "; ".join(blocking)
        else:
            summary = _(
                "%(rooms)s rooms at %(hotel)s from %(checkin)s to %(checkout)s for "
                "%(holder)s: about %(total)s %(currency)s."
            ) % {
                "rooms": len(reservations),
                "hotel": prop.name,
                "checkin": checkin,
                "checkout": checkout,
                "holder": holder["name"],
                "total": total,
                "currency": currency.name,
            }
        return {
            "summary": summary,
            "period": {"date_from": checkin, "date_to": nights[-1]},
            "definitions": [
                _(
                    "Rooms are picked among those free for every night with room for "
                    "the adults, in the order of the automatic assignment."
                ),
                _(
                    "The estimate includes taxes, the room and the board; tourist "
                    "taxes are added by the PMS on confirmed reservations."
                ),
            ],
            "warnings": [
                _(
                    "Lab tool: only for staging. Nothing is sent to the guest, the "
                    "channel manager or any authority."
                )
            ]
            + warnings,
            "result": result,
            "plan": {
                "blocking": blocking,
                "folio": folio,
                "reservations": reservations,
                "estimate": total,
            },
        }

    def _ai_lab_group_booking_create_apply(self, plan, **arguments):
        self._lab_check()
        if plan["blocking"]:
            raise UserError(_("Nothing created: %s") % "; ".join(plan["blocking"]))
        prop = self.env["pms.property"].browse(plan["folio"]["pms_property_id"])
        planned = [vals["preferred_room_id"] for vals in plan["reservations"]]
        with lab_silence(self.with_company(prop.company_id).sudo()) as quiet:
            folio = quiet.env["pms.folio"].create(plan["folio"])
            Reservation = quiet.env["pms.reservation"]
            reservations = Reservation
            for vals in plan["reservations"]:
                # One by one: in a batch every reservation gets the same name
                # and the create overrides only see the last one.
                reservations |= Reservation.create(dict(vals, folio_id=folio.id))
            quiet.env.flush_all()
            if (
                reservations.filtered(lambda r: r.splitted or r.overbooking)
                or sorted(reservations.preferred_room_id.ids) != sorted(planned)
                or len(set(reservations.mapped("name"))) != len(reservations)
            ):
                raise UserError(
                    _("The reservations differ from the preview: nothing was saved.")
                )
            ses_removed = self._lab_group_drop_ses(quiet.env, reservations)
        reservations = reservations.sorted("id")
        difference = folio.currency_id.round(folio.amount_total - plan["estimate"])
        return {
            "summary": _(
                "Folio %(name)s created with %(count)s reservations: %(total)s "
                "%(currency)s."
            )
            % {
                "name": folio.name,
                "count": len(reservations),
                "total": folio.amount_total,
                "currency": folio.currency_id.name,
            },
            "warnings": [
                _("%s SES communications were removed: nothing goes to SES.")
                % ses_removed
            ]
            if ses_removed
            else [],
            "result": {
                "folio": {
                    "id": folio.id,
                    "name": folio.name,
                    "state": folio.state,
                    "amount_total": folio.amount_total,
                    "url": self._lab_url(folio),
                },
                "reservations": [
                    {
                        "id": reservation.id,
                        "name": reservation.name,
                        "room_type": reservation.room_type_id.default_code,
                        "room": reservation.preferred_room_id.name,
                        "state": reservation.state,
                        "total": reservation.price_total + reservation.price_services,
                    }
                    for reservation in reservations
                ],
                "estimate": plan["estimate"],
                "difference": difference,
            },
        }

    @api.model
    def _lab_group_drop_ses(self, env, reservations):
        """Remove the SES communications the PMS queued for the lab group."""
        if "pms.ses.communication" not in env:
            return 0
        Communication = env["pms.ses.communication"].sudo()
        if "reservation_id" not in Communication._fields:
            return 0
        pending = Communication.search(
            [("reservation_id", "in", reservations.ids), ("state", "=", "to_send")]
        )
        count = len(pending)
        pending.unlink()
        return count
