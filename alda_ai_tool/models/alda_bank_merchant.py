from odoo import fields, models

JOURNAL_TYPES = [
    ("ta", "Card terminal (TA)"),
    ("va", "Payment provider P&S (VA)"),
    ("wa", "Kiosk (WA)"),
]


class AldaBankMerchant(models.Model):
    """Journal a merchant number of a hotel settles, as confirmed by a user.

    Written by the AI tool alda_bank_sabadell_merchant after the user
    confirms it, and read by the Sabadell reconciliation tools.
    """

    _name = "alda.bank.merchant"
    _description = "Merchant number of a hotel's card settlements"
    _order = "property_id, merchant"
    _rec_name = "merchant"

    property_id = fields.Many2one(
        "pms.property", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="property_id.company_id", store=True)
    merchant = fields.Char(
        string="Merchant number",
        required=True,
        help="Digits of the merchant number, without leading zeros.",
    )
    journal_type = fields.Selection(JOURNAL_TYPES, required=True)
    confirmed_by_id = fields.Many2one("res.users", readonly=True)

    _sql_constraints = [
        (
            "property_merchant_uniq",
            "unique(property_id, merchant)",
            "This merchant number is already stored for the hotel.",
        ),
    ]
