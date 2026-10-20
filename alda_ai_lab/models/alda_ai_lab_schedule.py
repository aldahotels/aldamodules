import calendar
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.base.models.res_partner import _tz_get
from odoo.addons.pms_ai_tool.tools import get_guard

from .lab import lab_enabled

_logger = logging.getLogger(__name__)

PERIODS = {
    "yesterday": "Yesterday",
    "previous_week": "Previous week (Monday to Sunday)",
    "previous_month": "Previous month",
    "month_to_date": "Current month up to yesterday",
    "last_7_days": "Last 7 days",
    "last_30_days": "Last 30 days",
    "next_7_days": "Next 7 days (from today)",
    "next_week": "Next week (Monday to Sunday)",
    "next_month": "Next month",
}
FREQUENCIES = {"daily": "Every day", "weekly": "Every week", "monthly": "Every month"}
WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
# Arguments of a catalogue tool that a schedule knows how to fill.
FILLABLE_ARGUMENTS = {
    "date_from",
    "date_to",
    "property_ids",
    "property_id",
    "salesperson_ids",
}


def period_dates(period, today):
    """First and last day of a relative period seen from ``today``."""
    one_day = timedelta(days=1)
    if period == "yesterday":
        return today - one_day, today - one_day
    if period == "previous_week":
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if period == "previous_month":
        end = today.replace(day=1) - one_day
        return end.replace(day=1), end
    if period == "month_to_date":
        # On the 1st, the month so far is empty: take the previous month.
        end = today - one_day
        return end.replace(day=1), end
    if period == "last_7_days":
        return today - timedelta(days=7), today - one_day
    if period == "last_30_days":
        return today - timedelta(days=30), today - one_day
    if period == "next_7_days":
        return today, today + timedelta(days=6)
    if period == "next_week":
        start = today + timedelta(days=7 - today.weekday())
        return start, start + timedelta(days=6)
    if period == "next_month":
        start = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        following = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, following - one_day
    raise ValueError(f"Unknown period {period}")


class AldaAiLabSchedule(models.Model):
    _name = "alda.ai.lab.schedule"
    _description = "AI lab scheduled report"
    _order = "state, next_run, id"

    name = fields.Char(compute="_compute_name", store=True)
    user_id = fields.Many2one(
        "res.users",
        string="Owner",
        required=True,
        default=lambda self: self.env.user,
        ondelete="cascade",
        help="Who asked for the report.",
    )
    recipient_ids = fields.Many2many(
        "res.users",
        relation="alda_ai_lab_schedule_recipient_rel",
        column1="schedule_id",
        column2="user_id",
        string="Recipients",
        help="Each recipient gets the report in their chat with OdooBot, computed "
        "with their own permissions.",
    )
    tool_id = fields.Many2one(
        "ai.tool", string="Report", required=True, ondelete="cascade"
    )
    period = fields.Selection(list(PERIODS.items()), required=True)
    frequency = fields.Selection(list(FREQUENCIES.items()), required=True)
    weekday = fields.Selection([(day, day.capitalize()) for day in WEEKDAYS])
    day_of_month = fields.Integer(help="For monthly reports; 31 means the last day.")
    time_of_day = fields.Float(string="Time", required=True, default=8.0)
    tz = fields.Selection(
        _tz_get,
        string="Timezone",
        required=True,
        default=lambda self: self.env.user.tz or "Europe/Madrid",
    )
    property_ids = fields.Many2many(
        "pms.property",
        relation="alda_ai_lab_schedule_property_rel",
        column1="schedule_id",
        column2="property_id",
        string="Properties",
    )
    salesperson_ids = fields.Many2many(
        "res.users",
        relation="alda_ai_lab_schedule_salesperson_rel",
        column1="schedule_id",
        column2="user_id",
        string="Salespeople",
    )
    state = fields.Selection(
        [("active", "Active"), ("paused", "Paused"), ("cancelled", "Cancelled")],
        default="active",
        required=True,
    )
    next_run = fields.Datetime(readonly=True)
    last_run = fields.Datetime(readonly=True)
    last_state = fields.Selection(
        [("ok", "Sent"), ("error", "Failed")], string="Last result", readonly=True
    )
    last_error = fields.Char(readonly=True)
    run_count = fields.Integer(readonly=True)

    @api.depends(
        "tool_id", "period", "frequency", "weekday", "day_of_month", "time_of_day"
    )
    def _compute_name(self):
        for schedule in self:
            schedule.name = " · ".join(
                part
                for part in (
                    "IA",
                    schedule.tool_id.name or "",
                    PERIODS.get(schedule.period, ""),
                    schedule._lab_when(),
                )
                if part
            )

    def _lab_when(self):
        """Human description of when the report goes out."""
        self.ensure_one()
        hour, minute = self._lab_hour_minute()
        at = "%02d:%02d" % (hour, minute)
        if self.frequency == "weekly":
            return f"{(self.weekday or '').capitalize()} {at}"
        if self.frequency == "monthly":
            return _("Day %(day)s %(at)s") % {"day": self.day_of_month or 1, "at": at}
        return _("Daily %s") % at

    def _lab_hour_minute(self):
        self.ensure_one()
        return divmod(min(round((self.time_of_day or 0) * 60), 24 * 60 - 1), 60)

    # Scheduling

    def _lab_runs_on(self, day):
        self.ensure_one()
        if self.frequency == "daily":
            return True
        if self.frequency == "weekly":
            return WEEKDAYS[day.weekday()] == self.weekday
        last_day = calendar.monthrange(day.year, day.month)[1]
        return day.day == min(self.day_of_month or 1, last_day)

    def _lab_next_run(self, after):
        """First run strictly after ``after`` (naive UTC), as naive UTC.

        The time is local wall-clock time: across a change of time the run
        stays at the same local hour, which ir.cron intervals do not do.
        """
        self.ensure_one()
        tz = pytz.timezone(self.tz or "UTC")
        hour, minute = self._lab_hour_minute()
        local_after = pytz.utc.localize(after).astimezone(tz)
        day = local_after.date()
        for _offset in range(370):
            if self._lab_runs_on(day):
                local = tz.localize(
                    datetime.combine(day, time(hour, minute)), is_dst=False
                )
                if local > local_after:
                    return local.astimezone(pytz.utc).replace(tzinfo=None)
            day += timedelta(days=1)
        raise UserError(_("The schedule never runs: check its frequency."))

    def _lab_set_next_run(self, after):
        """Plan the next run and wake the dispatcher up right then."""
        for schedule in self:
            schedule.next_run = schedule._lab_next_run(after)
            cron = self.env.ref(
                "alda_ai_lab.ir_cron_lab_dispatch", raise_if_not_found=False
            )
            if cron:
                # Without it the 5-minute interval decides when the report
                # goes out. An inactive cron ignores the trigger.
                cron.sudo()._trigger(at=schedule.next_run)

    def _lab_next_runs(self, count=3):
        """The next ``count`` runs, in the schedule's timezone, as text."""
        self.ensure_one()
        tz = pytz.timezone(self.tz or "UTC")
        runs, after = [], fields.Datetime.now()
        for _index in range(count):
            after = self._lab_next_run(after)
            runs.append(
                pytz.utc.localize(after).astimezone(tz).strftime("%a %Y-%m-%d %H:%M")
            )
        return runs

    def _lab_local_today(self):
        self.ensure_one()
        tz = pytz.timezone(self.tz or "UTC")
        return pytz.utc.localize(fields.Datetime.now()).astimezone(tz).date()

    # Arguments of the catalogue tool

    @api.model
    def _lab_tool_guard(self, tool):
        model = tool.sudo().model_id.model
        if not model or model not in self.env:
            return None
        return get_guard(getattr(self.env[model], tool.sudo().function_name, None))

    @api.model
    def _lab_check_schedulable(self, tool, property_ids=None):
        """Refuse tools a schedule cannot run on its own."""
        guard = self._lab_tool_guard(tool)
        if not guard or guard["write"]:
            raise UserError(
                _("Only read tools of the catalogue can be scheduled: %s is not one.")
                % tool.name
            )
        if tool.sudo().model_id.model.startswith("alda.ai.lab."):
            raise UserError(_("The lab tools cannot be scheduled."))
        if not guard["log_result"]:
            # Its answer is personal data: it stays out of the MCP log and
            # must stay out of a chat as well.
            raise UserError(
                _("The tool %s returns personal data and cannot be scheduled.")
                % tool.name
            )
        missing = [
            name
            for name in guard["required"]
            if name not in FILLABLE_ARGUMENTS
            or (name == "property_id" and len(property_ids or []) != 1)
        ]
        if missing:
            raise UserError(
                _(
                    "The tool %(tool)s needs arguments a schedule cannot fill: "
                    "%(missing)s."
                )
                % {"tool": tool.name, "missing": ", ".join(missing)}
            )
        return guard

    def _lab_tool_arguments(self, today=None):
        """Arguments for the catalogue tool on the day of the run."""
        self.ensure_one()
        guard = self._lab_check_schedulable(self.tool_id, self.property_ids.ids)
        schema = guard["input_schema"]
        date_from, date_to = period_dates(self.period, today or self._lab_local_today())
        arguments = {}
        if "date_from" in schema:
            arguments["date_from"] = date_from.isoformat()
        if "date_to" in schema:
            arguments["date_to"] = date_to.isoformat()
        if self.property_ids and "property_ids" in schema:
            arguments["property_ids"] = self.property_ids.ids
        if len(self.property_ids) == 1 and "property_id" in schema:
            arguments["property_id"] = self.property_ids.id
        if self.salesperson_ids and "salesperson_ids" in schema:
            arguments["salesperson_ids"] = self.salesperson_ids.ids
        return arguments

    # Running

    def _lab_recipients(self):
        self.ensure_one()
        return (self.recipient_ids or self.user_id).filtered(
            lambda user: user.active and not user.share
        )

    def _lab_send(self):
        """Run the report for every recipient and post it to their chat."""
        self.ensure_one()
        failed = []
        for user in self._lab_recipients():
            # In the recipient's language and timezone, also from the cron.
            context = {"lang": user.lang, "tz": user.tz}
            Report = self.env["alda.ai.lab.report.tools"].with_context(**context)
            arguments = self._lab_tool_arguments()
            try:
                response = (
                    self.tool_id.with_user(user)
                    .with_context(**context)
                    ._execute_tool(**arguments)
                )
                body = Report._lab_render_report(self, response, user)
            except Exception as error:  # noqa: B902 - reported to the user
                failed.append(f"{user.name}: {error}")
                body = Report._lab_render_failure(self, error)
            Report._lab_post_to_chat(user, body)
        self.sudo().write(
            {
                "last_run": fields.Datetime.now(),
                "last_state": "error" if failed else "ok",
                "last_error": "; ".join(failed)[:500] or False,
                "run_count": self.run_count + 1,
            }
        )
        return not failed

    @api.model
    def _lab_dispatch(self):
        """Send the reports that are due (scheduled action of the module)."""
        if not lab_enabled(self.env):
            return
        now = fields.Datetime.now()
        for schedule in self.sudo().search(
            [("state", "=", "active"), ("next_run", "<=", now)]
        ):
            try:
                with self.env.cr.savepoint():
                    schedule._lab_send()
            except Exception:  # noqa: B902 - one bad schedule must not stop others
                _logger.exception("Scheduled AI report %s failed", schedule.id)
                schedule.write({"last_run": now, "last_state": "error"})
            # Move on even after a failure: no retry storm every minute.
            schedule._lab_set_next_run(now)
