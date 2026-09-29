# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import Command, api, models

_logger = logging.getLogger(__name__)

# Admin-level groups that must never be granted by default to new internal
# users. They are removed from the template user (base.default_user), whose
# groups are the default groups of every new internal user. Groups whose
# module is not installed are skipped.
TEMPLATE_BLOCKED_GROUPS = (
    "account.group_account_manager",
    "hr.group_hr_manager",
    "hr_contract.group_hr_contract_manager",
    "purchase.group_purchase_manager",
    "stock.group_stock_manager",
    "point_of_sale.group_pos_manager",
    "project.group_project_manager",
    "sales_team.group_sale_manager",
    "website.group_website_designer",
    "helpdesk.group_helpdesk_manager",
    "base.group_allow_export",
    "base.group_partner_manager",
    "sql_request_abstract.group_sql_request_user",
    "sql_request_abstract.group_sql_request_manager",
    "base.group_system",
    "base.group_erp_manager",
)

# Members of this group (and therefore of base.group_system, which implies
# it) keep "Technical Features" once base.group_user stops implying it.
NO_ONE_ANCHOR_GROUP = "base.group_erp_manager"


class ResGroups(models.Model):
    _inherit = "res.groups"

    @api.model
    def _alda_security_baseline_apply(self):
        """Apply the whole security baseline. Idempotent, safe to re-run.

        The template sanitization runs first: the template may hold an admin
        group that implies base.group_no_one, and the group_no_one cleanup
        must see the template without it.
        """
        groups = self.sudo()
        groups._alda_security_baseline_sanitize_template()
        groups._alda_security_baseline_group_no_one()
        return True

    @api.model
    def _alda_security_baseline_blocked_groups(self):
        """Return the existing groups of TEMPLATE_BLOCKED_GROUPS."""
        blocked = self.browse()
        for xmlid in TEMPLATE_BLOCKED_GROUPS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group and group._name == "res.groups":
                blocked |= group
        return blocked

    @api.model
    def _alda_security_baseline_sanitize_template(self):
        """Remove the blocked admin-level groups from the template user.

        The removal is written on the group side, so it never goes through
        ``res.users.write``: existing users keep their groups (the core only
        propagates groups *added* to the template) and no role or template
        propagation logic is triggered.

        A blocked group implied by another group that stays in the template
        is kept, with a warning: new users would get it back through the
        implication anyway, and leaving the template without an implied
        group makes the next edit of the template propagate that group to
        every active internal user.

        :return: the groups removed from the template
        """
        template = self.env.ref("base.default_user", raise_if_not_found=False)
        if not template:
            return self.browse()
        template = template.sudo().with_context(active_test=False)
        if "role_line_ids" in template._fields and template.role_line_ids:
            _logger.warning(
                "The template user has role lines: its groups are governed by "
                "roles and will be rewritten from them. Sanitize the roles "
                "assigned to the template instead."
            )
        to_remove = self._alda_security_baseline_blocked_groups() & template.groups_id
        while to_remove:
            reimplied = to_remove & (template.groups_id - to_remove).trans_implied_ids
            if not reimplied:
                break
            _logger.warning(
                "Template groups %s are implied by other template groups and "
                "are kept.",
                ", ".join(sorted(reimplied.mapped("full_name"))),
            )
            to_remove -= reimplied
        if to_remove:
            to_remove.with_context(active_test=False).write(
                {"users": [Command.unlink(template.id)]}
            )
            _logger.info(
                "Removed groups %s from the template user.",
                ", ".join(sorted(to_remove.mapped("full_name"))),
            )
        return to_remove

    @api.model
    def _alda_security_baseline_group_no_one(self):
        """Stop granting "Technical Features" to every internal user.

        The core makes base.group_user imply base.group_no_one. This removes
        that implication, makes the anchor group imply it instead (so user
        administrators and administrators keep it), and then removes
        base.group_no_one from every user who does not get it through another
        group. The last step always runs, so a re-run also cleans memberships
        left behind by a manual revert or by explicit per-user grants.

        :return: the users that lost base.group_no_one
        """
        no_one = self.env.ref("base.group_no_one")
        internal = self.env.ref("base.group_user")
        anchor = self.env.ref(NO_ONE_ANCHOR_GROUP)
        # First: guarantee the anchor members keep the group.
        anchor._apply_group(no_one)
        if no_one in internal.implied_ids:
            internal.write({"implied_ids": [Command.unlink(no_one.id)]})
        no_one = no_one.with_context(active_test=False)
        stale_users = no_one.users.filtered(
            lambda user: no_one not in (user.groups_id - no_one).trans_implied_ids
        )
        if stale_users:
            no_one.write({"users": [Command.unlink(uid) for uid in stale_users.ids]})
            _logger.info(
                "Removed group %s from %d users: %s",
                no_one.full_name,
                len(stale_users),
                stale_users.ids,
            )
        return stale_users
