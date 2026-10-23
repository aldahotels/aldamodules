# Copyright 2025 Consultores Hoteleros Integrales Alda Hotels
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
import logging
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import _, api, fields, models, tools

_logger = logging.getLogger(__name__)

# Motivos que implican "bloqueo real" (para DETECTAR y CLASIFICAR)
# Debe coincidir con la detección en helpdesk_ticket._is_room_blocked
BLOCK_REASONS = {"Avería", "Maintenance", "Mantenimiento programado", "Plaga"}


def _date_range(start, end):
    """Inclusive range of date objects."""
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def _maximal_runs(sorted_dates):
    """Split sorted dates into maximal consecutive runs [(start, end), ...]."""
    runs = []
    if not sorted_dates:
        return runs
    start = prev = sorted_dates[0]
    for d in sorted_dates[1:]:
        if d == prev + timedelta(days=1):
            prev = d
        else:
            runs.append((start, prev))
            start = prev = d
    runs.append((start, prev))
    return runs


class PmsBlockEpisode(models.Model):
    """Room block episode: a contiguous period of
    time during which a room is blocked."""

    _name = "pms.block.episode"
    _description = "Room Block Episode"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    room_id = fields.Many2one(
        comodel_name="pms.room",
        string="Room",
        required=True,
        index=True,
        tracking=True,
    )
    pms_property_id = fields.Many2one(
        comodel_name="pms.property",
        string="Property",
        required=True,
        index=True,
        tracking=True,
        help="Property at the time the episode was recorded (snapshot).",
    )
    closure_reason_id = fields.Many2one(
        comodel_name="room.closure.reason",
        string="Closure Reason",
        ondelete="restrict",
        tracking=True,
        help="Closure reason of the block at the time it was observed (snapshot).",
    )
    closure_reason_name = fields.Char(
        string="Closure Reason (snapshot)",
        help="Literal name of the closure reason at the time the episode was "
        "recorded, preserved in case the reason is later renamed.",
    )
    date_start = fields.Date(
        string="Start (first blocked night)",
        required=True,
        index=True,
        tracking=True,
    )
    date_end = fields.Date(
        string="End (first unblocked night)",
        tracking=True,
        help="First night on which the room was again available. Empty while "
        "the block is in progress. Convention [start, end).",
    )
    last_observed_date = fields.Date(
        string="Last Observed Blocked Night",
        readonly=True,
        help="Last night on which the reconciliation process actually observed "
        "this block. Used to close the episode; never re-derived from the "
        "source reservations after the fact.",
    )
    state = fields.Selection(
        selection=[("open", "Open"), ("closed", "Closed")],
        compute="_compute_state",
        store=True,
    )
    duration_days = fields.Integer(
        string="Duration (nights)",
        compute="_compute_duration_days",
        store=True,
        help="Number of blocked nights (date_end - date_start) once the "
        "episode is closed; zero while open.",
    )
    origin_reservation_id = fields.Many2one(
        comodel_name="pms.reservation",
        string="Origin Reservation",
        ondelete="set null",
        readonly=True,
        help="Reference to the out-of-service reservation that gave rise to "
        "this episode. Set to null if the reservation is deleted; the "
        "episode is preserved.",
    )
    ticket_ids = fields.Many2many(
        comodel_name="helpdesk.ticket",
        relation="pms_block_episode_ticket_rel",
        column1="episode_id",
        column2="ticket_id",
        string="Related Tickets",
        help="Tickets related to this block episode. The link does not imply "
        "that the ticket caused the block; causality is only set on the "
        "ticket classification by an authorized user.",
    )
    ticket_count = fields.Integer(compute="_compute_ticket_count")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "room_date_start_uniq",
            "unique(room_id, date_start)",
            "An episode for this room already starts on that date.",
        ),
    ]

    @api.depends("room_id", "date_start")
    def _compute_name(self):
        for ep in self:
            ep.name = "%s · %s" % (
                ep.room_id.display_name if ep.room_id else "?",
                ep.date_start or "?",
            )

    @api.depends("date_end")
    def _compute_state(self):
        for ep in self:
            ep.state = "closed" if ep.date_end else "open"

    @api.depends("date_start", "date_end")
    def _compute_duration_days(self):
        for ep in self:
            if ep.date_start and ep.date_end:
                ep.duration_days = (ep.date_end - ep.date_start).days
            else:
                ep.duration_days = 0

    @api.depends("ticket_ids")
    def _compute_ticket_count(self):
        for ep in self:
            ep.ticket_count = len(ep.ticket_ids)

    def _auto_init(self):
        """Create partial unique index: at most one open episode per room."""
        res = super()._auto_init()
        if not tools.index_exists(self._cr, "pms_block_episode_one_open_per_room"):
            self._cr.execute(
                'CREATE UNIQUE INDEX "pms_block_episode_one_open_per_room" '
                'ON "%s" (room_id) WHERE date_end IS NULL' % self._table
            )
        return res

    # Reconciliation engine

    @api.model
    def _cron_reconcile_block_episodes(self):
        """Daily entry point (independent cron, does not touch the existing one)."""
        self._reconcile_block_episodes()

    @api.model
    def _reconcile_block_episodes(self, today=None):
        """Idempotently reconciles room block episodes.

        Creates missing episodes, extends ongoing blocks, closes unobserved
        blocks using the last observed night, and never modifies closed episodes.
        Repeated runs produce the same result.
        """
        today = today or fields.Date.context_today(self)
        room_nights = self._get_blocked_nights_by_room(today)

        # Process rooms with open episodes plus rooms currently observed
        # blocked, so a block whose lines were shortened or deleted is closed.
        room_ids = set(room_nights.keys()) | set(
            self.search([("date_end", "=", False)]).mapped("room_id").ids
        )
        for room_id in sorted(room_ids):
            self._reconcile_room(room_id, room_nights.get(room_id, {}), today)

    @api.model
    def _get_blocked_nights_by_room(self, today):
        """Return {room_id: {date: reservation_line}} for all blocked nights ≤ today.

        Uses the same criteria as the current helpdesk detection (overnight
        room, out reservation, state not draft/cancel, admitted motive names).
        """
        lines = (
            self.env["pms.reservation.line"]
            .sudo()
            .search(
                [
                    ("date", "<=", today),
                    ("overnight_room", "=", True),
                    ("reservation_id.state", "not in", ["draft", "cancel"]),
                    ("reservation_id.reservation_type", "=", "out"),
                ]
            )
        )
        result = {}
        for line in lines:
            reason = line.reservation_id.closure_reason_id
            if not reason or reason.name not in BLOCK_REASONS:
                continue
            result.setdefault(line.room_id.id, {})[line.date] = line
        return result

    def _reconcile_room(self, room_id, nights_map, today):
        """Reconcile episodes for a single room."""
        runs = _maximal_runs(sorted(nights_map.keys()))
        open_ep = self.search(
            [("room_id", "=", room_id), ("date_end", "=", False)], limit=1
        )

        # Nights already covered by existing episodes.
        covered = self._get_covered_nights(room_id)

        # Current run that reaches today (if any).
        current_run = self._find_current_run(runs, today)

        # 1. Refresh or close the open episode.
        if open_ep:
            self._update_open_episode(open_ep, current_run, today, nights_map, covered)
        else:
            # No open episode, but there might be a current run to create.
            pass

        # Create episodes for uncovered nights in the current run only.
        if current_run:
            self._create_new_episodes(room_id, current_run, covered, nights_map, today)

        covered = set()
        eps = self.search([("room_id", "=", room_id)])
        for ep in eps:
            if ep.date_end:
                covered |= set(
                    _date_range(ep.date_start, ep.date_end - timedelta(days=1))
                )
            elif ep.last_observed_date:
                covered |= set(_date_range(ep.date_start, ep.last_observed_date))
        return covered

    def _find_current_run(self, runs, today):
        """Find the run that contains today (if any)."""
        for run_start, run_end in runs:
            if run_start <= today <= run_end:
                return (run_start, run_end)
        return None

    def _update_open_episode(self, open_ep, current_run, today, nights_map, covered):
        """Refresh open episode or close it if block ended/gap detected."""
        if current_run:
            last_obs = open_ep.last_observed_date or open_ep.date_start
            if current_run[0] <= last_obs + timedelta(days=1):
                # Block continues: extend observation to the end of the run.
                new_last = max(
                    open_ep.last_observed_date or open_ep.date_start, current_run[1]
                )
                if new_last != open_ep.last_observed_date:
                    open_ep.last_observed_date = new_last
                    # Keep original motive snapshot; do not overwrite.
                    if not open_ep.origin_reservation_id:
                        first_line = nights_map.get(current_run[0])
                        if first_line:
                            open_ep.origin_reservation_id = first_line.reservation_id.id
                    if not open_ep.closure_reason_id:
                        first_line = nights_map.get(current_run[0])
                        if first_line:
                            reason = first_line.reservation_id.closure_reason_id
                            open_ep.closure_reason_id = reason.id
                            open_ep.closure_reason_name = reason.name or ""
                    covered = set(
                        _date_range(open_ep.date_start, open_ep.last_observed_date)
                    )
                    return covered
                else:
                    # Gap between last observation and current run:
                    # close old, will create new below.
                    self._close_episode(open_ep, today, reason="gap")
                    return covered
            else:
                # No current run → block ended.
                self._close_episode(open_ep, today, reason="ended")
                return covered

    def _create_new_episodes(self, room_id, current_run, covered, nights_map, today):
        """Create episodes for uncovered nights in the current run."""
        run_nights = set(_date_range(current_run[0], current_run[1]))
        uncovered = sorted(run_nights - covered)
        if uncovered:
            subruns = _maximal_runs(uncovered)
            for sub_start, sub_end in subruns:
                self._create_episode(
                    room_id, sub_start, sub_end, nights_map, today, is_open=True
                )

    def _close_episode(self, ep, today, reason):
        """Close an open episode, using the last observed night."""
        last = ep.last_observed_date or ep.date_start
        ep.date_end = last + timedelta(days=1)
        note = _(
            "Episodio cerrado: el bloqueo ya no se observa en la reconciliación de hoy."
        )
        if ep.origin_reservation_id and ep.origin_reservation_id.state == "cancel":
            note += " " + _("La reserva origen está cancelada.")
        elif not ep.origin_reservation_id:
            note += " " + _("La reserva origen ya no existe.")
        if reason == "gap":
            note += " " + _(
                "Se detectó un hueco entre la última observación y el bloqueo actual "
                "(posible modificación retroactiva del origen)."
            )
        ep.message_post(body=note)

    def _create_episode(
        self, room_id, date_start, date_end, nights_map, today, is_open
    ):
        """Create an episode for the given run. Idempotent via unique constraint."""
        if self.search_count(
            [("room_id", "=", room_id), ("date_start", "=", date_start)]
        ):
            return self.env["pms.block.episode"]

        # Determine motive and origin from the most recent night in the run.
        reason = False
        reservation = False
        for d in sorted(nights_map.keys(), reverse=True):
            if date_start <= d <= date_end:
                line = nights_map[d]
                reason = line.reservation_id.closure_reason_id
                reservation = line.reservation_id
                break

        room = self.env["pms.room"].browse(room_id)
        vals = {
            "room_id": room_id,
            "pms_property_id": room.pms_property_id.id,
            "closure_reason_id": reason.id if reason else False,
            "closure_reason_name": reason.name if reason else "",
            "origin_reservation_id": reservation.id if reservation else False,
            "date_start": date_start,
            "last_observed_date": date_end,
        }
        if is_open:
            vals["date_end"] = False
        else:
            vals["date_end"] = date_end + timedelta(days=1)

        try:
            with self.env.cr.savepoint():
                ep = self.create(vals)
        except IntegrityError:
            # Another concurrent execution created it.
            ep = self.search(
                [("room_id", "=", room_id), ("date_start", "=", date_start)], limit=1
            )

        if not is_open:
            ep.message_post(
                body=_("Episodio detectado tras su fin (reconciliación a posteriori).")
            )
        return ep

    # Ticket linking (forward-only, never retroactive, never infer causality)
    def _link_tickets_to_episodes(self, episodes):
        """Link tickets created during the episode and classify them by block motive.

        Forward-only: links tickets created while the episode is open or
        closed in the current pass. Confirmed motives are classified as
        'confirmed'; all others as 'related'.
        """
        Ticket = self.env["helpdesk.ticket"].sudo()
        for ep in episodes:
            if not ep.ticket_ids:
                continue
            last_night = ep.last_observed_date or ep.date_start
            # Tickets whose creation date falls within the episode's observed nights.
            tickets = Ticket.search(
                [
                    ("pms_room_id", "=", ep.room_id.id),
                    (
                        "create_date",
                        ">=",
                        fields.Datetime.to_string(
                            fields.Datetime.from_string(str(ep.date_start))
                            - timedelta(days=0)
                        ),
                    ),
                    (
                        "create_date",
                        "<",
                        fields.Datetime.to_string(
                            fields.Datetime.from_string(str(last_night))
                            + timedelta(days=1)
                        ),
                    ),
                    ("id", "not in", ep.ticket_ids.ids),
                ]
            )
            for ticket in tickets:
                ep.ticket_ids = [(4, ticket.id)]
                # Automatic classification based on episode motive
                if ep.closure_reason_id.name in BLOCK_REASONS:
                    ticket.block_classification = (
                        "confirmed"  # Bloqueo relevante confirmado
                    )
                else:
                    ticket.block_classification = "related"  # Bloqueo irrelevante

    def action_view_chatter(self):
        """Open chatter (mail.message) filtered for this episode."""
        self.ensure_one()
        return {
            "name": _("Chatter del Episodio"),
            "type": "ir.actions.act_window",
            "res_model": "mail.message",
            "view_mode": "list,form",
            "domain": [("model", "=", self._name), ("res_id", "=", self.id)],
            "context": {"default_model": self._name, "default_res_id": self.id},
            "target": "current",
        }

    def action_export_chatter(self):
        """Export chatter of this episode to CSV/XLSX."""
        self.ensure_one()
        return {
            "name": _("Exportar Chatter del Episodio"),
            "type": "ir.actions.act_window",
            "res_model": "mail.message",
            "view_mode": "list",
            "domain": [("model", "=", self._name), ("res_id", "=", self.id)],
            "context": {"default_model": self._name, "default_res_id": self.id},
            "target": "new",
            "flags": {"mode": "readonly"},
        }


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    block_episode_ids = fields.Many2many(
        comodel_name="pms.block.episode",
        relation="pms_block_episode_ticket_rel",
        column1="ticket_id",
        column2="episode_id",
        string="Block Episodes",
        help="Episodes of room block linked to this ticket.",
        readonly=True,
    )
    block_episode_count = fields.Integer(compute="_compute_block_episode_count")
    block_classification = fields.Selection(
        [
            ("common", "Avería común"),
            ("related", "Bloqueo irrelevante"),
            ("confirmed", "Bloqueo relevante confirmado"),
        ],
        default="common",
        tracking=True,
        index=True,
        copy=False,
        string="Clasificación de bloqueo",
    )

    @api.depends("block_episode_ids")
    def _compute_block_episode_count(self):
        for t in self:
            t.block_episode_count = len(t.block_episode_ids)
