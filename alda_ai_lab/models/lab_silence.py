"""Switches that make the lab silent. All of them do nothing outside it."""

from odoo import _, api, models

from .lab import lab_silent, lab_tripwire


class PmsNotificationMixin(models.AbstractModel):
    # Event rules send emails and WhatsApp messages synchronously, inside
    # create and write of folios, reservations, invoices and payments.
    _inherit = "pms.notification.mixin"

    def _pms_notification_prepare_pre_domain_matches(
        self, event_type, changed_fields=None
    ):
        if lab_silent():
            return {}
        return super()._pms_notification_prepare_pre_domain_matches(
            event_type, changed_fields=changed_fields
        )

    def _pms_notification_run_event_rules(
        self, event_type, changed_fields=None, pre_domain_matches=None
    ):
        if lab_silent():
            return True
        return super()._pms_notification_run_event_rules(
            event_type,
            changed_fields=changed_fields,
            pre_domain_matches=pre_domain_matches,
        )


class BaseAutomation(models.Model):
    # Automated actions defined in the database run on create and write of any
    # model and can send emails; no context key turns them off.
    _inherit = "base.automation"

    def _get_actions(self, records, triggers):
        if lab_silent():
            return self.browse()
        return super()._get_actions(records, triggers)


class MailMail(models.Model):
    _inherit = "mail.mail"

    @api.model_create_multi
    def create(self, vals_list):
        # Some senders create the email and send it at once, before the
        # final check of the lab could stop it.
        lab_tripwire(_("create an email"))
        return super().create(vals_list)


class PmsFolio(models.Model):
    _inherit = "pms.folio"

    def action_cancel(self):
        # Cancelling rectifies downpayments and notifies the guest.
        lab_tripwire(_("cancel a folio"))
        return super().action_cancel()


class PmsReservation(models.Model):
    _inherit = "pms.reservation"

    def action_cancel(self):
        lab_tripwire(_("cancel reservations"))
        return super().action_cancel()


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        # Posting sends invoices to the SII and moves downpayments.
        lab_tripwire(_("post accounting entries"))
        return super()._post(soft=soft)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_post(self):
        lab_tripwire(_("post a payment"))
        return super().action_post()

    def action_draft(self):
        lab_tripwire(_("reset a payment to draft"))
        return super().action_draft()
