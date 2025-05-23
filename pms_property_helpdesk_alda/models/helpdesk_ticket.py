from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskPmsProperty(models.Model):
    _inherit = "helpdesk.ticket"

    pms_property_id = fields.Many2one(
        comodel_name="pms.property",
        string="Property",
        store=True,
        required=True,
        index=True,
    )

    pms_room_id = fields.Many2one(
        comodel_name="pms.room",
        string="Room",
        domain="[('pms_property_id', '=', pms_property_id)]",
        store=True,
        index=True,
    )

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields, attributes)
        employee = self.env["hr.employee"].search(
            [("user_id", "=", self.env.uid)], limit=1
        )
        if employee and "pms_property_id" in res:
            res["pms_property_id"]["domain"] = [("id", "in", employee.property_ids.ids)]
        return res

    @api.onchange("pms_property_id")
    def _onchange_pms_property(self):
        self.pms_room_id = False
        return {
            "domain": {
                "pms_room_id": [("pms_property_id", "=", self.pms_property_id.id)]
            }
        }

    @api.constrains("pms_property_id", "pms_room_id")
    def _check_property_assignment(self):
        for ticket in self:
            if ticket.pms_property_id:
                employee = self.env["hr.employee"].search(
                    [("user_id", "=", ticket.env.uid)], limit=1
                )
                if employee and ticket.pms_property_id not in employee.property_ids:
                    raise ValidationError(
                        _("You do not have permission to assign this property.")
                    )

            if (
                ticket.pms_room_id
                and ticket.pms_room_id.pms_property_id != ticket.pms_property_id
            ):
                raise ValidationError(
                    _("The selected room does not belong to the specified hotel.")
                )

            if ticket.pms_room_id and not ticket.pms_property_id:
                raise ValidationError(
                    _("You must select a hotel before assigning a room.")
                )
