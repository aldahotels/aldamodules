# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from xml.dom import ValidationErr
from odoo.exceptions import UserError
from odoo import _, models, fields
import logging


_logger = logging.getLogger(__name__)


class WizardCreateProperty(models.TransientModel):
    _name = "wizard.create.property"
    _description = "Easy Property Creation"

    company_id = fields.Many2one(
        string="Company",
        help="The company for folio",
        required=True,
        comodel_name="res.company",
    )
    name = fields.Char(string="Name", required=True)
    property_code = fields.Char(string="Code (4 characters)", required=True)
    account_code = fields.Char(string="Account Code (3 numbers)", required=True)
    bank_ids = fields.Many2many(
        comodel_name="res.partner.bank",
        string="Banks",
    )
    tpv1_bank_id = fields.Many2one(
        string="TPV 1 Bank",
        help="Bank linked with TPV1 payments",
        comodel_name="res.partner.bank",
        domain="[('id', 'in', bank_ids)]"
    )
    tpv2_bank_id = fields.Many2one(
        string="TPV 2 Bank",
        help="Bank linked with TPV2 payments",
        comodel_name="res.partner.bank",
        domain="[('id', 'in', bank_ids)]"
    )
    tpv3_bank_id = fields.Many2one(
        string="TPV 3 Bank",
        help="Bank linked with 2 payments",
        comodel_name="res.partner.bank",
        domain="[('id', 'in', bank_ids)]"
    )
    ps_bank_id = fields.Many2one(
        string="Redsys Bank",
        help="Bank linked with Redsys Gateway payments",
        comodel_name="res.partner.bank",
        domain="[('id', 'in', bank_ids)]"
    )
    booking_bank_id = fields.Many2one(
        string="Bank linked with Booking.com Gateway payments",
        comodel_name="res.partner.bank",
        domain="[('id', 'in', bank_ids)]"
    )
    default_pricelist_id = fields.Many2one(
        string="Product Pricelist",
        help="The default pricelist used in this property.",
        comodel_name="product.pricelist",
        required=True,
        default=lambda self: self.env.ref("product.list0").id,
    )

    def create_property(self):
        pms_property = self.env["pms.property"].create({
            "name": self.name,
            "company_id": self.company_id.id,
        })
        pms_property.default_pricelist_id = self.default_pricelist_id.id
        pms_property.folio_sequence_id.prefix = "F" + self.property_code + "/%(y)s"
        pms_property.checkin_sequence_id.prefix = "C" + self.property_code + "/%(y)s"

        Journals = self.env["account.journal"]

        # Customer Invoices
        default_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", "70500000000"),
        ])
        customer_journal = Journals.create({
            "name": "Clientes " + self.name,
            "type": "sale",
            "pms_property_ids": [(4, pms_property.id)],
            "code": self.property_code,
            "check_chronology": True,
            "refund_sequence": True,
            "default_account_id": default_account_id.id,
            "sequence": 5,
        })
        pms_property.journal_normal_invoice_id = customer_journal.id

        # Simplified Invoices
        default_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", "70500000000"),
        ])
        simplified_journal = Journals.create({
            "name": "Simplificadas " + self.name,
            "type": "sale",
            "pms_property_ids": [(4, pms_property.id)],
            "code": "FS" + self.property_code,
            "check_chronology": True,
            "refund_sequence": True,
            "default_account_id": default_account_id.id,
            "sequence": 6,
        })
        pms_property.journal_simplified_invoice_id = simplified_journal.id

        # Supplier Invoices
        default_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", "60000000000"),
        ])
        Journals.create({
            "name": "Proveedores " + self.name,
            "type": "purchase",
            "pms_property_ids": [(4, pms_property.id)],
            "code": "FS" + self.property_code,
            "check_chronology": True,
            "refund_sequence": True,
            "default_account_id": default_account_id.id,
            "sequence": 7,
        })

        # BANKS
        bank_sequence = 13
        for bank in self.bank_ids:
            if "SABADELL" in bank.bank_id.name.upper():
                bank_code = "SA"
                bank_name = "Sabadell"
                bank_digit = "1"
            elif "CAIXABANK" in bank.bank_id.name.upper():
                bank_code = "CB"
                bank_name = "Caixabank"
                bank_digit = "2"
            elif "ABANCA" in bank.bank_id.name.upper():
                bank_code = "CB"
                bank_name = "A"
                bank_digit = "3"
            else:
                bank_code = bank.bank_id.bic[:2]
                bank_name = bank.bank_name
                bank_digit = "3"

            duplicate_journal = self.env["account.journal"].search([
                ("code", "=", bank_code + self.property_code)
            ])
            if duplicate_journal:
                raise UserError(
                    _("Journal with code %s already exist",
                    bank_code + self.property_code
                ))

            default_code = "5720000"
            default_account_code = default_code + bank_digit + self.account_code
            default_account_id = self.env["account.account"].search([
                ("company_id", "=", self.company_id.id),
                ("code", "=", default_account_code),
            ], limit=1)
            if not default_account_id:
                account_reference = self.env["account.account"].search([
                    ("code", "ilike", default_code),
                    ("company_id", "=", self.company_id.id),
                ], limit=1)
                default_account_id = account_reference.copy()
                default_account_id.code = default_account_code
                default_account_id.name = "CC " + bank_name + " " + self.name + " " + bank.acc_number[-4:]

            suspense_code = "5720080"
            suspense_account_code = suspense_code + bank_digit + self.account_code
            suspense_account_id = self.env["account.account"].search([
                ("company_id", "=", self.company_id.id),
                ("code", "=", suspense_account_code),
            ], limit=1)
            if not suspense_account_id:
                account_reference = self.env["account.account"].search([
                    ("code", "ilike", suspense_code),
                    ("company_id", "=", self.company_id.id),
                ], limit=1)
                suspense_account_id = account_reference.copy()
                suspense_account_id.code = suspense_account_code
                suspense_account_id.name = "Transitoria " + bank_name + " " + self.name + " " + bank.acc_number[-4:]

            payment_code = "5720090"
            payment_account_code = payment_code + bank_digit + self.account_code
            payment_account_id = self.env["account.account"].search([
                ("company_id", "=", self.company_id.id),
                ("code", "=", payment_account_code),
            ], limit=1)
            if not payment_account_id:
                account_reference = self.env["account.account"].search([
                    ("code", "ilike", payment_code),
                    ("company_id", "=", self.company_id.id),
                ], limit=1)
                payment_account_id = account_reference.copy()
                payment_account_id.code = payment_account_code
                payment_account_id.name = "Pendientes " + bank_name + " " + self.name + " " + bank.acc_number[-4:]

            bank_journal = Journals.create({
                "name": default_account_id.name ,
                "type": "bank",
                "pms_property_ids": [(4, pms_property.id)],
                "code": bank_code + self.property_code,
                "default_account_id": default_account_id.id,
                "suspense_account_id": suspense_account_id.id,
                "payment_credit_account_id": payment_account_id.id,
                "payment_debit_account_id": payment_account_id.id,
                "bank_account_id": bank.id,
                "sequence": bank_sequence,
            })
            bank_sequence += 1

            # TPV1 Journal
            if self.tpv1_bank_id and self.tpv1_bank_id.id == bank.id:
                journal = Journals.create({
                    "name": "TPV " + self.name + " " + bank.acc_number[-4:],
                    "type": "bank",
                    "pms_property_ids": [(4, pms_property.id)],
                    "code": "TPV" + self.property_code,
                    "default_account_id": default_account_id.id,
                    "suspense_account_id": suspense_account_id.id,
                    "payment_credit_account_id": payment_account_id.id,
                    "payment_debit_account_id": payment_account_id.id,
                    "allowed_pms_payments": True,
                    "sequence": 8,
                })

            # TPV2 Journal
            if self.tpv2_bank_id and self.tpv2_bank_id.id == bank.id:
                journal = Journals.create({
                    "name": "TPV " + self.name + " " + bank.acc_number[-4:],
                    "type": "bank",
                    "pms_property_ids": [(4, pms_property.id)],
                    "code": "TPV" + self.property_code,
                    "default_account_id": default_account_id.id,
                    "suspense_account_id": suspense_account_id.id,
                    "payment_credit_account_id": payment_account_id.id,
                    "payment_debit_account_id": payment_account_id.id,
                    "allowed_pms_payments": True,
                    "sequence": 9,
                })

            # TPV3 Journal
            if self.tpv3_bank_id and self.tpv3_bank_id.id == bank.id:
                journal = Journals.create({
                    "name": "TPV " + self.name + " " + bank.acc_number[-4:],
                    "type": "bank",
                    "pms_property_ids": [(4, pms_property.id)],
                    "code": "TPV" + self.property_code,
                    "default_account_id": default_account_id.id,
                    "suspense_account_id": suspense_account_id.id,
                    "payment_credit_account_id": payment_account_id.id,
                    "payment_debit_account_id": payment_account_id.id,
                    "allowed_pms_payments": True,
                    "sequence": 10,
                })

            # Redsys Journal
            if self.ps_bank_id.id == bank.id:
                ps_journal = Journals.create({
                    "name": "P&S Redsys " + self.name + " " + bank.acc_number[-4:],
                    "type": "bank",
                    "pms_property_ids": [(4, pms_property.id)],
                    "code": "PS" + self.property_code,
                    "default_account_id": default_account_id.id,
                    "suspense_account_id": suspense_account_id.id,
                    "payment_credit_account_id": payment_account_id.id,
                    "payment_debit_account_id": payment_account_id.id,
                    "sequence": 11,
                })

            # Booking.com Journal
            if self.booking_bank_id.id == bank.id:
                payment_code = "43000000005"
                payment_account_id = self.env["account.account"].search([
                    ("code", "ilike", payment_code),
                    ("company_id", "=", self.company_id.id),
                ])

                default_code = "57201099"
                default_account_code = default_code + self.account_code
                default_account_id = self.env["account.account"].search([
                    ("company_id", "=", self.company_id.id),
                    ("code", "=", default_account_code),
                ], limit=1)
                if not default_account_id:
                    account_reference = self.env["account.account"].search([
                        ("code", "ilike", default_code),
                        ("company_id", "=", self.company_id.id),
                    ], limit=1)
                    default_account_id = account_reference.copy()
                    default_account_id.code = default_account_code
                    default_account_id.name = "CC Virtual Booking " + self.name

                tpv_journal = Journals.create({
                    "name": "Booking " + self.name  + " " + bank.acc_number[-4:],
                    "type": "bank",
                    "pms_property_ids": [(4, pms_property.id)],
                    "code": "BK" + self.property_code,
                    "default_account_id": default_account_id.id,
                    "suspense_account_id": suspense_account_id.id,
                    "payment_credit_account_id": payment_account_id.id,
                    "payment_debit_account_id": payment_account_id.id,
                })

        # CASH"
        default_code = "57000000"
        default_account_code = default_code + self.account_code
        default_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", default_account_code),
        ])
        if not default_account_id:
            account_reference = self.env["account.account"].search([
                ("code", "ilike", default_code),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
            default_account_id = account_reference.copy()
            default_account_id.code = default_account_code
            default_account_id.name = "Efectivo " + self.name

        suspense_code = "57000800"
        suspense_account_code = suspense_code + self.account_code
        suspense_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", suspense_account_code),
        ], limit=1)
        if not suspense_account_id:
            account_reference = self.env["account.account"].search([
                ("code", "ilike", suspense_code),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
            suspense_account_id = account_reference.copy()
            suspense_account_id.code = suspense_account_code
            suspense_account_id.name = "Transitoria Caja " + self.name

        payment_code = "57000900"
        payment_account_code = payment_code + self.account_code
        payment_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", payment_account_code),
        ], limit=1)
        if not payment_account_id:
            account_reference = self.env["account.account"].search([
                ("code", "ilike", payment_code),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
            payment_account_id = account_reference.copy()
            payment_account_id.code = payment_account_code
            payment_account_id.name = "Pendientes Caja " + self.name

        profit_account_code = "77800000000"
        profit_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", profit_account_code),
        ])

        loss_account_code = "67800000000"
        loss_account_id = self.env["account.account"].search([
            ("company_id", "=", self.company_id.id),
            ("code", "=", loss_account_code),
        ])

        cash_journal = Journals.create({
            "name": "Caja " + self.name ,
            "type": "cash",
            "pms_property_ids": [(4, pms_property.id)],
            "code": "CJ" + self.property_code,
            "default_account_id": default_account_id.id,
            "suspense_account_id": suspense_account_id.id,
            "payment_credit_account_id": payment_account_id.id,
            "payment_debit_account_id": payment_account_id.id,
            "profit_account_id": profit_account_id.id,
            "loss_account_id": loss_account_id.id,
            "allowed_pms_payments": True,
            "sequence": 12,
        })
