import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HelpdeskPmsEnterprise(models.Model):
    _inherit = "helpdesk.ticket"

    pms_property_id = fields.Many2one(
        comodel_name="pms.property",
        string="Property",
        store=True,
        tracking=True,
        domain=lambda self: [("id", "in", self._get_allowed_property_ids())],
        help="The hotel associated with this ticket.",
    )

    pms_room_id = fields.Many2one(
        comodel_name="pms.room",
        string="Room",
        domain="[('pms_property_id', '=', pms_property_id)]",
        tracking=True,
        help="The room associated with this ticket. It must belong to the selected property.",
    )

    has_allowed_properties = fields.Boolean(
        string="Tiene propiedades permitidas",
        compute="_compute_has_allowed_properties",
        store=False,
    )

    @api.depends("team_id")
    def _compute_has_allowed_properties(self):
        for ticket in self:
            allowed_property_ids = self.env.context.get("allowed_pms_property_ids")
            company_ids = (
                self.env.context.get("allowed_company_ids") or self.env.company.ids
            )
            if allowed_property_ids:
                domain = [("id", "in", allowed_property_ids)]
                if company_ids:
                    domain += [("company_id", "in", company_ids), ("active", "=", True)]
                property_ids = self.env["pms.property"].sudo().search(domain)
                ticket.has_allowed_properties = bool(property_ids)
            else:
                ticket.has_allowed_properties = False

    def _get_allowed_property_ids(self):
        allowed_property_ids = self.env.context.get("allowed_pms_property_ids")
        allowed_property_ids = self.env.context.get("allowed_pms_property_ids")
        company_ids = (
            self.env.context.get("allowed_company_ids") or self.env.company.ids
        )
        if allowed_property_ids:
            domain = [("id", "in", allowed_property_ids)]
            if company_ids:
                domain += [("company_id", "in", company_ids), ("active", "=", True)]
                property_ids = self.env["pms.property"].sudo().search(domain)
                self.has_allowed_properties = True
                self.has_allowed_properties = bool(property_ids)

            return property_ids.ids
        return self.env.user.pms_property_ids.ids

    @api.onchange("pms_property_id")
    def _onchange_pms_property_id(self):
        for ticket in self:
            old_property = ticket._origin.pms_property_id if ticket._origin else False

            if (
                ticket.pms_room_id
                and ticket.pms_room_id.pms_property_id != ticket.pms_property_id
            ):
                ticket.pms_room_id = False

            if ticket._origin and ticket._origin.id:
                new_property = ticket.pms_property_id

                if old_property != new_property:
                    if old_property and old_property.partner_id:
                        ticket.message_unsubscribe(
                            partner_ids=[old_property.partner_id.id]
                        )

                    if new_property and new_property.partner_id:
                        existing_followers = ticket.message_follower_ids.filtered(
                            lambda f: f.partner_id == new_property.partner_id
                        )
                        if not existing_followers:
                            ticket.message_subscribe(
                                partner_ids=[new_property.partner_id.id]
                            )

    @api.constrains("pms_property_id", "pms_room_id")
    def _check_property_consistency(self):
        for ticket in self:
            if (
                ticket.pms_room_id
                and ticket.pms_room_id.pms_property_id != ticket.pms_property_id
            ):
                raise ValidationError(
                    _("The selected room does not belong to the specified property.")
                )

            if ticket.pms_property_id:
                allowed_property_ids = ticket._get_allowed_property_ids()
                if ticket.pms_property_id.id not in allowed_property_ids:
                    raise ValidationError(
                        _("You do not have permission to assign this property.")
                    )

            if ticket.pms_room_id and not ticket.pms_property_id:
                raise ValidationError(
                    _("You must select a hotel before assigning a room.")
                )

    @api.model
    def create(self, vals):
        ticket = super().create(vals)
        if ticket.pms_property_id and ticket.pms_property_id.partner_id:
            ticket.message_subscribe(partner_ids=[ticket.pms_property_id.partner_id.id])
        return ticket

    def write(self, vals):
        old_properties = {}
        if "pms_property_id" in vals:
            for ticket in self:
                old_properties[ticket.id] = ticket.pms_property_id

        result = super().write(vals)

        if "pms_property_id" in vals:
            for ticket in self:
                old_property = old_properties.get(ticket.id)
                new_property = ticket.pms_property_id

                if old_property != new_property:
                    self._manage_property_followers(ticket, old_property, new_property)

        return result

    def _manage_property_followers(self, ticket, old_property, new_property):
        try:

            if old_property and old_property.partner_id:
                ticket.message_unsubscribe(partner_ids=[old_property.partner_id.id])

            if new_property and new_property.partner_id:
                existing_followers = ticket.message_follower_ids.filtered(
                    lambda f: f.partner_id == new_property.partner_id
                )
                if not existing_followers:
                    ticket.message_subscribe(partner_ids=[new_property.partner_id.id])

        except Exception as e:
            _logger.error(
                "Error managing property followers for ticket %s: %s", ticket.id, str(e)
            )
