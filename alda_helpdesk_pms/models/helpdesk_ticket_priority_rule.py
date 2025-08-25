from odoo import api, fields, models


class HelpdeskPriorityRule(models.Model):
    _name = "helpdesk.ticket.priority.rule"
    _description = "Priority Rules Based on Conditions"
    _rec_name = "rule_name"

    type_rule = fields.Selection(
        [
            ("no_room", "Not Room"),
            ("unblocked", "Unblocked Room"),
            ("blocked_room", "Blocked Room"),
        ],
        string="Types Ruler",
        required=True,
    )
    block_category = fields.Selection(
        [
            ("low", "Blocked Low"),
            ("medium", "Blocked Medium"),
            ("high", "Blocked High"),
        ],
        string="Category Blocked",
        default="low",
        required=True,
        compute="_compute_block_category",
        store=True,
    )

    occupancy_category = fields.Selection(
        [
            ("low", "Occupancy Low"),
            ("medium", "Occupancy Medium"),
            ("high", "Occupancy High"),
        ],
        string="Category Occupancy",
        default="low",
        required=True,
        compute="_compute_block_category",
        store=True,
    )

    rule_name = fields.Char(
        string="Name Ruler", compute="_compute_rule_name", store=True
    )

    is_pms_property = fields.Selection(
        [("30", "Yes"), ("0", "No")],
        string="Managed by PMS?",
        default="30",
        readonly=True,
        required=True,
    )

    is_room_related = fields.Selection(
        [("20", "Yes"), ("0", "No")], string="Room Related?", default="0", required=True
    )

    is_room_blocked = fields.Selection(
        [("30", "Yes"), ("0", "No")], string="Room Blocked?", default="0", required=True
    )

    days_blocked = fields.Selection(
        [
            ("0", "0 days"),
            ("300", "1 to 15 days"),
            ("400", "16 to 30 days"),
            ("500", "More than 30 days"),
        ],
        string="Days Room Blocked",
        default="0",
        required=True,
    )

    occupancy_rate = fields.Selection(
        [("5", "0% to 30%"), ("15", "31% to 70%"), ("30", "71% to 100%")],
        string="Occupancy Rate (%)",
        default="5",
        required=True,
    )

    block_rate = fields.Selection(
        [("100", "0% to 30%"), ("1000", "31% to 70%"), ("10000", "71% to 100%")],
        string="Block Rate (%)",
        default="100",
        required=True,
    )

    season = fields.Selection(
        [("5", "Low Season"), ("20", "High Season")],
        string="Season of the Year",
        default="5",
        required=True,
    )

    is_room_operated_normaly = fields.Selection(
        [("20", "Yes"), ("0", "No")], string="Room Operating Normally?", default="20"
    )

    is_property_operated_normaly = fields.Selection(
        [("20", "Yes"), ("0", "No")],
        string="Property Operating Normally?",
        default="20",
    )

    priority_estimated = fields.Selection(
        [("0", "Low"), ("1", "Medium"), ("2", "High"), ("3", "Urgent")],
        string="Estimated Priority",
        default="0",
        required=True,
    )

    priority_suggestion_action = fields.Html(string="Suggested Action", required=True)

    _sql_constraints = [
        (
            "unique_combination",
            "unique(type_rule, "
            "is_pms_property, "
            "block_category, "
            "occupancy_category, "
            "is_room_related, "
            "is_room_blocked, "
            "days_blocked, "
            "occupancy_rate, "
            "block_rate, "
            "season, "
            "is_room_operated_normaly, "
            "is_property_operated_normaly)",
            "Each combination must be unique.",
        )
    ]

    @api.depends("block_rate", "occupancy_rate")
    def _compute_block_category(self):
        for record in self:
            rate = int(record.block_rate or 0)
            occupancy_rate = int(record.occupancy_rate or 0)
            if rate <= 100:
                record.block_category = "low"
            elif rate <= 1000:
                record.block_category = "medium"
            else:
                record.block_category = "high"
            if occupancy_rate <= 5:
                record.occupancy_category = "low"
            elif occupancy_rate <= 15:
                record.occupancy_category = "medium"
            else:
                record.occupancy_category = "high"

    @api.depends("type_rule", "block_category")
    def _compute_rule_name(self):
        label = dict(self.fields_get(allfields=["type_rule"])["type_rule"]["selection"])
        category = dict(
            self.fields_get(allfields=["block_category"])["block_category"]["selection"]
        )
        for record in self:
            user_text = label.get(record.type_rule, "")
            category_text = category.get(record.block_category, "")
            record.rule_name = f"{user_text} - {category_text} - Rule #{record.id}"

    @api.onchange("type_rule")
    def _onchange_type_rule(self):
        for record in self:
            if record.type_rule == "blocked_room":
                record.is_room_blocked = "30"
                record.is_room_related = "20"
                record.is_property_operated_normaly = "20"
                record.is_room_operated_normaly = "0"
            elif record.type_rule == "unblocked":
                record.is_room_blocked = "0"
                record.is_room_related = "20"
                record.is_property_operated_normaly = "20"
                record.is_room_operated_normaly = "20"
            else:
                record.is_room_blocked = "0"
                record.is_room_related = "0"
                record.is_room_operated_normaly = "20"

    @api.model
    def create(self, vals):
        vals = self._apply_type_rule_defaults(vals)
        record = super().create(vals)
        return record

    def write(self, vals):
        vals = self._apply_type_rule_defaults(vals)
        return super().write(vals)

    def _apply_type_rule_defaults(self, vals):
        type_rule = vals.get("type_rule")
        if type_rule == "blocked_room":
            vals.update(
                {
                    "is_room_blocked": "30",
                    "is_room_related": "20",
                    "is_property_operated_normaly": "20",
                    "is_room_operated_normaly": "0",
                }
            )
        elif type_rule == "unblocked":
            vals.update(
                {
                    "is_room_blocked": "0",
                    "is_room_related": "20",
                    "is_property_operated_normaly": "20",
                    "is_room_operated_normaly": "20",
                }
            )
        elif type_rule == "no_room":
            vals.update(
                {
                    "is_room_blocked": "0",
                    "is_room_related": "0",
                    "is_room_operated_normaly": "20",
                }
            )
        return vals
