from collections import Counter

from markupsafe import Markup
from psycopg2 import errors as pg_errors

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_repr

from odoo.addons.pms_ai_tool.tools import guarded_tool

from .lab import lab_silence

MAX_DAYS = 62
MAX_CANDIDATES = 200
MAX_RESERVATIONS = 50
IDS = {"type": "array", "items": {"type": "integer"}}

UPDATE_INPUT = {
    "date_from": {
        "type": "string",
        "format": "date",
        "description": "First night of the window (today or later).",
    },
    "date_to": {
        "type": "string",
        "format": "date",
        "description": "Last night of the window, included, at most %s days "
        "after date_from." % MAX_DAYS,
    },
    "discount_percent": {
        "type": "number",
        "minimum": 0.01,
        "maximum": 100,
        "description": "Discount for the nights inside the window. Nights that "
        "already have this discount or more are left as they are.",
    },
    "property_ids": dict(IDS, maxItems=20),
    "agency_id": {"type": "integer"},
    "partner_id": {
        "type": "integer",
        "description": "Guest or holder of the folio.",
    },
    "folio_ids": dict(IDS, maxItems=50),
    "reservation_ids": dict(IDS, maxItems=50),
    "room_type_ids": dict(IDS, maxItems=20),
    "sale_channel_ids": dict(IDS, maxItems=10),
    "max_reservations": {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_RESERVATIONS,
        "description": f"Refuse if more reservations qualify ({MAX_RESERVATIONS}).",
    },
}
SELECTORS = (
    "agency_id",
    "partner_id",
    "folio_ids",
    "reservation_ids",
    "room_type_ids",
    "sale_channel_ids",
)
INVOICED_FOLIOS_QUERY = """
SELECT DISTINCT fsl.folio_id
  FROM folio_sale_line fsl
  JOIN folio_sale_line_invoice_rel rel ON rel.sale_line_id = fsl.id
  JOIN account_move_line aml ON aml.id = rel.invoice_line_id
  JOIN account_move am ON am.id = aml.move_id
 WHERE fsl.folio_id = ANY(%(folio_ids)s)
   AND am.state <> 'cancel'
"""


class AldaAiLabReservationTools(models.AbstractModel):
    _name = "alda.ai.lab.reservation.tools"
    _inherit = "alda.ai.lab.mixin"
    _description = "AI lab tools: bulk changes of reservations"

    @api.model
    def _lab_room_total(self, reservation, new_discounts=None):
        """Mirror of the room total of the PMS with other night discounts."""
        new_discounts = new_discounts or {}
        currency = reservation.currency_id
        lines = reservation.reservation_line_ids
        discount = 0.0
        for line in lines:
            percent = new_discounts.get(line.id, line.discount) or 0.0
            first = line.price * percent * 0.01
            discount += (
                first + (line.price - first) * (line.cancel_discount or 0.0) * 0.01
            )
        room = sum(lines.mapped("price"))
        if room <= 0:
            return 0.0
        taxes = reservation.tax_ids.compute_all(
            room - currency.round(discount),
            currency,
            1,
            product=reservation.room_type_id.product_id,
        )
        return currency.round(taxes["total_included"])

    @api.model
    def _lab_candidates(self, property_ids, date_from, date_to, **selectors):
        domain = [
            ("pms_property_id", "in", property_ids),
            ("checkin", "<=", date_to),
            ("checkout", ">", date_from),
        ]
        if selectors.get("agency_id"):
            domain.append(("agency_id", "=", selectors["agency_id"]))
        if selectors.get("partner_id"):
            domain += [
                "|",
                ("partner_id", "=", selectors["partner_id"]),
                ("folio_id.partner_id", "=", selectors["partner_id"]),
            ]
        for argument, field in (
            ("folio_ids", "folio_id"),
            ("reservation_ids", "id"),
            ("room_type_ids", "room_type_id"),
            ("sale_channel_ids", "sale_channel_origin_id"),
        ):
            if selectors.get(argument):
                domain.append((field, "in", selectors[argument]))
        Reservation = self.env["pms.reservation"]
        if Reservation.search_count(domain) > MAX_CANDIDATES:
            raise UserError(
                _(
                    "More than %s reservations match: narrow the window or the "
                    "selection."
                )
                % MAX_CANDIDATES
            )
        return Reservation.search(domain, order="checkin, id")

    @api.model
    def _lab_exclusion(self, reservation, today, invoiced, window, percent):
        """Why a reservation is left out, or the nights to change."""
        folio = reservation.folio_id
        if reservation.state not in ("draft", "confirm"):
            return _("its state is %s") % reservation.state, None
        if reservation.reservation_type != "normal":
            return _("it is not a normal reservation"), None
        if reservation.checkin < today:
            return _("the stay has started"), None
        if reservation.blocked:
            return _("it is blocked by the channel manager"), None
        if reservation.overbooking:
            return _("it is in overbooking"), None
        if folio.state not in ("draft", "sent", "confirm"):
            return _("its folio is %s") % folio.state, None
        if folio.id in invoiced:
            return _("its folio has invoices"), None
        nights = reservation.reservation_line_ids.filtered(
            lambda line: window[0] <= line.date <= window[1]
        )
        if any(line.is_reselling for line in nights):
            return _("some nights are being resold"), None
        if not nights.filtered(lambda line: line.price > 0):
            return _("its nights in the window are free"), None
        to_change = nights.filtered(lambda line: (line.discount or 0) < percent)
        if not to_change:
            return _("its nights already have this discount or more"), None
        current = self._lab_room_total(reservation)
        if float_compare(
            current,
            reservation.price_total,
            precision_rounding=reservation.currency_id.rounding,
        ):
            return _("its stored total does not match its nights"), None
        return None, to_change

    @guarded_tool(
        input_schema=UPDATE_INPUT,
        output_schema={
            "changes": {"type": "array", "items": {"type": "object"}},
            "excluded": {"type": "array", "items": {"type": "object"}},
            "excluded_by_reason": {"type": "object"},
            "totals": {"type": "object"},
        },
        required_inputs=["date_from", "date_to", "discount_percent"],
        write=True,
        apply="_ai_lab_reservations_bulk_update_apply",
        timeout_ms=60000,
    )
    def _ai_lab_reservations_bulk_update(
        self,
        date_from,
        date_to,
        discount_percent,
        property_ids=None,
        max_reservations=MAX_RESERVATIONS,
        **selectors,
    ):
        self._lab_check()
        Tools = self.env["pms.ai.tools"]
        period = Tools._ai_check_period(date_from, date_to, MAX_DAYS)
        if not any(selectors.get(name) for name in SELECTORS):
            raise UserError(
                _(
                    "Say which reservations: an agency, a partner, folios, reservations, "
                    "room types or sale channels."
                )
            )
        props = Tools._ai_scope_property_ids(property_ids)
        today = fields.Date.context_today(self)
        if date_from < today:
            raise UserError(_("The window must start today or later."))
        reservations = self._lab_candidates(props, date_from, date_to, **selectors)
        missing = set(selectors.get("reservation_ids") or []) - set(reservations.ids)
        invoiced = set()
        if reservations:
            invoiced = {
                row["folio_id"]
                for row in Tools._ai_fetch(
                    INVOICED_FOLIOS_QUERY, {"folio_ids": reservations.folio_id.ids}
                )
            }
        changes, excluded, binding, rows = [], [], [], []
        for reservation in reservations:
            reason, to_change = self._lab_exclusion(
                reservation, today, invoiced, (date_from, date_to), discount_percent
            )
            if reason:
                excluded.append({"reservation": reservation.name, "reason": reason})
                continue
            before = reservation.price_total
            after = self._lab_room_total(
                reservation, dict.fromkeys(to_change.ids, discount_percent)
            )
            changes.append(
                {
                    "reservation_id": reservation.id,
                    "reservation": reservation.name,
                    "folio": reservation.folio_id.name,
                    "property": reservation.pms_property_id.name,
                    "checkin": reservation.checkin,
                    "checkout": reservation.checkout,
                    "room_type": reservation.room_type_id.default_code,
                    "channel": reservation.sale_channel_origin_id.name,
                    "nights_changed": len(to_change),
                    "room_total_before": before,
                    "room_total_after": after,
                    "impact": reservation.currency_id.round(after - before),
                }
            )
            binding.append(
                [
                    reservation.id,
                    reservation.write_date.isoformat(),
                    float_repr(before, 2),
                    float_repr(after, 2),
                    sorted(
                        [line.id, float_repr(line.discount or 0.0, 2)]
                        for line in to_change
                    ),
                ]
            )
            rows.append(
                {
                    "id": reservation.id,
                    "line_ids": to_change.ids,
                    "before": {line.id: line.discount for line in to_change},
                    "after_room": after,
                }
            )
        limit = max_reservations or MAX_RESERVATIONS
        if len(changes) > limit:
            raise UserError(
                _(
                    "%(count)s reservations qualify and the limit is %(limit)s: narrow "
                    "the selection or raise max_reservations."
                )
                % {"count": len(changes), "limit": limit}
            )
        total_before = sum(row["room_total_before"] for row in changes)
        total_after = sum(row["room_total_after"] for row in changes)
        warnings = [
            _(
                "Lab tool: only for staging. Nothing is sent to the guests or to the "
                "channel manager."
            )
        ]
        if missing:
            warnings.append(
                _("Reservations not found or not accessible: %s.")
                % ", ".join(map(str, sorted(missing)))
            )
        indirect = [
            row["reservation"]
            for row, reservation in zip(
                changes,
                self.env["pms.reservation"].browse([r["id"] for r in rows]),
                strict=True,
            )
            if reservation.sale_channel_origin_id.channel_type == "indirect"
        ]
        if indirect:
            warnings.append(
                _(
                    "%s reservations come from agencies or OTAs: in production the "
                    "change would not reach the channel manager, which could "
                    "overwrite it."
                )
                % len(indirect)
            )
        reasons = Counter(row["reason"] for row in excluded)
        return {
            "summary": _(
                "%(count)s reservations get %(percent)s%% off their nights from "
                "%(date_from)s to %(date_to)s: %(before).2f → %(after).2f "
                "(%(impact).2f); %(excluded)s left out."
            )
            % {
                "count": len(changes),
                "percent": discount_percent,
                "date_from": date_from,
                "date_to": date_to,
                "before": total_before,
                "after": total_after,
                "impact": total_after - total_before,
                "excluded": len(excluded),
            },
            "period": period,
            "definitions": [
                _(
                    "Room totals include taxes; board and other services do not "
                    "change."
                ),
                _(
                    "Left out: reservations not pending (cancelled, checked in or "
                    "out), not normal, blocked, in overbooking, already started, with "
                    "an invoiced folio or with a total that does not match its nights."
                ),
            ],
            "warnings": warnings,
            "result": {
                "changes": changes,
                "excluded": excluded[:MAX_RESERVATIONS],
                "excluded_by_reason": dict(reasons),
                "totals": {
                    "reservations": len(changes),
                    "room_total_before": round(total_before, 2),
                    "room_total_after": round(total_after, 2),
                    "impact": round(total_after - total_before, 2),
                },
            },
            "binding": {"discount": discount_percent, "rows": binding},
            "plan": {"discount": discount_percent, "rows": rows},
        }

    def _ai_lab_reservations_bulk_update_apply(self, plan, **arguments):
        self._lab_check()
        rows = plan["rows"]
        if not rows:
            raise UserError(_("No reservation to change."))
        reservations = (
            self.env["pms.reservation"].sudo().browse([r["id"] for r in rows])
        )
        try:
            # Fail fast if someone is changing them right now.
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(
                    "SELECT id FROM pms_reservation WHERE id = ANY(%s) FOR UPDATE NOWAIT",
                    [reservations.ids],
                )
        except (pg_errors.LockNotAvailable, pg_errors.SerializationFailure):
            raise UserError(
                _("These reservations are being changed right now: preview again.")
            ) from None
        percent = plan["discount"]
        before = {
            reservation.id: reservation.price_total for reservation in reservations
        }
        with lab_silence(self.env["pms.reservation.line"].sudo()) as lines:
            for row in rows:
                # The nights directly: a write on the reservation would also
                # resync tourist taxes and run its notification rules.
                lines.browse(row["line_ids"]).write({"discount": percent})
            lines.env.flush_all()
            reservations.invalidate_recordset(["price_total", "discount"])
            changed = []
            for row, reservation in zip(rows, reservations, strict=True):
                if float_compare(
                    reservation.price_total,
                    row["after_room"],
                    precision_rounding=reservation.currency_id.rounding,
                ):
                    raise UserError(
                        _(
                            "%(name)s would end at %(got)s instead of %(want)s: "
                            "nothing was saved."
                        )
                        % {
                            "name": reservation.name,
                            "got": reservation.price_total,
                            "want": row["after_room"],
                        }
                    )
                previous = ", ".join(
                    "%s: %g%%" % (lines.browse(int(line_id)).date, discount or 0)
                    for line_id, discount in sorted(row["before"].items())
                )
                reservation._message_log(
                    body=Markup("<p>%s</p>")
                    % _(
                        "AI lab: %(percent)s%% off %(nights)s nights by %(user)s "
                        "(before: %(previous)s)."
                    )
                    % {
                        "percent": percent,
                        "nights": len(row["line_ids"]),
                        "user": self.env.user.name,
                        "previous": previous,
                    }
                )
                changed.append(
                    {
                        "reservation": reservation.name,
                        "folio": reservation.folio_id.name,
                        "room_total_before": before[reservation.id],
                        "room_total_after": reservation.price_total,
                        "url": self._lab_url(reservation),
                    }
                )
        impact = sum(
            row["room_total_after"] - row["room_total_before"] for row in changed
        )
        return {
            "summary": _(
                "%(count)s reservations changed: %(impact).2f in total. The previous "
                "discounts are noted on each reservation."
            )
            % {"count": len(changed), "impact": impact},
            "result": {"changed": changed, "impact": round(impact, 2)},
        }
