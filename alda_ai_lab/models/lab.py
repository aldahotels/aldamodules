import contextvars
import os
from contextlib import contextmanager

from odoo import _, api, models
from odoo.exceptions import UserError

LAB_ENVIRONMENTS = ("devel", "test")
LAB_MODEL_PREFIX = "alda.ai.lab."
PARAM_LAB_ENABLED = "alda_ai_lab.enabled"

# Set only by lab_silence, inside the server process. A context key would not
# do: any user can send one through JSON-RPC and switch the automations off,
# and code that drops the context (with_context({}), with_env) would lose it.
_SILENT = contextvars.ContextVar("alda_ai_lab_silent", default=False)

LAB_CONTEXT = {
    # Channel manager listeners (connector_pms_wubook) skip their exports.
    "connector_no_export": True,
    # No followers, tracking messages or notification emails from mail.thread.
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_create_nosubscribe": True,
    "mail_notrack": True,
    "mail_auto_subscribe_no_notify": True,
    "mail_activity_quick_update": True,
    "mail_notify_force_send": False,
}
# Rows that mean that something would leave Odoo after the commit.
OUTBOX_MODELS = (
    "mail.mail",
    "sms.sms",
    "queue.job",
    "pms.notification.log",
    "lock.code",
    "mailing.trace",
)
# Work that modules stage for the commit: channel exports.
PRECOMMIT_KEYS = (
    "connector_pms_wubook.availability_buffer",
    "connector_pms_wubook.plan_rules_buffer",
    "connector_pms_wubook.pending_plan_rules",
    "connector_pms_wubook.pending_plan_avail",
)
# The smart lock module stages every new or changed reservation and, at the
# commit, only generates door codes for those its own check selects.
SMARTLOCK_KEY = "pms_smartlock.pending_sync_ids"


def lab_enabled(env):
    """Whether the lab tools may run in this database.

    They change data in bulk and prepare messages for real customers, so they
    only run where the container says it is not production (Doodba ``devel``
    or ``test``, which is staging) and the database has the lab switched on.
    A production container never passes the first check, and a new copy of
    the production database does not carry the switch.
    """
    if os.environ.get("DOODBA_ENVIRONMENT") not in LAB_ENVIRONMENTS:
        return False
    enabled = env["ir.config_parameter"].sudo().get_param(PARAM_LAB_ENABLED)
    return enabled in ("1", "True", "true")


def lab_silent():
    """Whether the current code runs inside ``lab_silence``."""
    return _SILENT.get()


def lab_tripwire(what):
    """Refuse an operation the lab must never trigger."""
    if lab_silent():
        raise UserError(
            _("AI lab stopped: this change would %s. Nothing was saved.") % what
        )


def _staged_leaks(env):
    """Keys of the work staged for the commit that would leave Odoo."""
    staged = env.cr.precommit.data
    leaks = [key for key in PRECOMMIT_KEYS if staged.get(key)]
    pending = staged.get(SMARTLOCK_KEY)
    if pending:
        Reservation = env["pms.reservation"].sudo()
        check = getattr(type(Reservation), "_should_have_lock_codes", None)
        reservations = Reservation.browse(list(pending)).exists()
        if not check or any(r._should_have_lock_codes() for r in reservations):
            leaks.append(SMARTLOCK_KEY)
    return leaks


def _outbox_marks(env):
    """The last id of each outbox model, to spot the rows created after it."""
    return {
        name: env[name]
        .sudo()
        .with_context(active_test=False)
        .search([], order="id desc", limit=1)
        .id
        or 0
        for name in OUTBOX_MODELS
        if name in env
    }


@contextmanager
def lab_silence(records):
    """Change data without anything leaving Odoo.

    Yields ``records`` with the lab context. Inside the block, the overrides
    of this module skip the notification rules (email and WhatsApp) and the
    automated actions, and refuse cancelling, posting and creating emails. At
    the end, pending computations are flushed in the lab context and the
    block fails if any outgoing work was queued: emails, SMS, background jobs,
    notification logs, smart lock codes or channel exports.
    """
    env = records.env
    marks = _outbox_marks(env)
    token = _SILENT.set(True)
    try:
        quiet = records.with_context(**LAB_CONTEXT)
        yield quiet
        # Computations left for the flush would otherwise run later, in an
        # environment without the lab context.
        quiet.env.flush_all()
        leaks = _staged_leaks(env)
        for name, last_id in marks.items():
            if (
                env[name]
                .sudo()
                .with_context(active_test=False)
                .search_count([("id", ">", last_id)])
            ):
                leaks.append(name)
        if leaks:
            # The rollback undoes the rows but not the work staged for the
            # commit, which would still run if the request commits.
            for key in (SMARTLOCK_KEY,) + PRECOMMIT_KEYS:
                env.cr.precommit.data.pop(key, None)
            raise UserError(
                _(
                    "AI lab stopped: the change would send or queue work outside "
                    "Odoo (%s). Nothing was saved."
                )
                % ", ".join(leaks)
            )
    finally:
        _SILENT.reset(token)


class AldaAiLabMixin(models.AbstractModel):
    _name = "alda.ai.lab.mixin"
    _description = "Alda AI lab helpers"

    @api.model
    def _lab_check(self):
        if not lab_enabled(self.env):
            raise UserError(
                _(
                    "The lab tools only run on staging, with the system parameter "
                    "%s switched on."
                )
                % PARAM_LAB_ENABLED
            )

    @api.model
    def _lab_url(self, record):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}/web#id={record.id}&model={record._name}&view_type=form"
