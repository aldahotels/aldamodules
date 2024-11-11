# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ...components.backend_adapter import DocuwareApi


class DocuwareBackend(models.Model):

    _name = "docuware.backend"
    _inherit = ["mail.thread", "connector.backend"]

    name = fields.Char(required=True)
    url = fields.Char(required=True)
    username = fields.Char(required=True)
    password = fields.Char(required=True)
    access_token = fields.Char()
    active = fields.Boolean(string="Active", default=True)
    webhook_user = fields.Char()
    webhook_password = fields.Char()
    docuware_company_ids = fields.One2many("docuware.company", "backend_id")
    docuware_property_ids = fields.One2many("docuware.property", "backend_id")
    docuware_payment_mode_ids = fields.One2many("docuware.payment.mode", "backend_id")
    execute_user_id = fields.Many2one("res.users", "User for the jobs")

    _sql_constraints = [
        (
            "unique_webhook_user",
            "unique(webhook_user)",
            "webhook user must be unique",
        )
    ]

    def import_cabinets(self):
        for backend_record in self:
            self.env["docuware.cabinet"].with_delay().import_cabinets(
                backend_record=backend_record
            )
        return True

    def generate_token(self):
        self.ensure_one()
        self.access_token = DocuwareApi(self.url).generate_access_token(
            self.username, self.password
        )

    def import_docuware_document(self, cabinet_id, document_id, document_type):
        self.ensure_one()
        new_delay = (
            self.env[document_type]
            .with_delay()
            .import_record(self, cabinet_id, document_id)
        )
        job = self.env["queue.job"].search([("uuid", "=", new_delay.uuid)], limit=1)
        job.message_subscribe(partner_ids=self.message_partner_ids.ids)

    def map_company(self, name):
        return self.docuware_company_ids.filtered(lambda r: r.name == name).company_id

    def map_property(self, name):
        map_records = self.docuware_property_ids.filtered(lambda r: r.name == name)
        if not map_records:
            raise ValidationError(_("Property with name {} not found").format(name))
        return map_records.property_id

    def map_payment_mode(self, name):
        return self.docuware_payment_mode_ids.filtered(
            lambda r: r.name == name
        ).payment_mode_id

    @api.model
    def cron_regenerate_access_token(self):
        for backend in self.env["docuware.backend"].search([("username", "!=", None)]):
            backend.generate_token()


class DocuwareCompany(models.Model):
    _name = "docuware.company"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True)
    backend_id = fields.Many2one("docuware.backend")

    _sql_constraints = [
        ("unique_name", "unique(name, backend_id)", "name should be unique")
    ]


class DocuwareProperty(models.Model):
    _name = "docuware.property"

    name = fields.Char(required=True)
    property_id = fields.Many2one("pms.property")
    backend_id = fields.Many2one("docuware.backend")

    _sql_constraints = [
        ("unique_name", "unique(name, backend_id)", "name should be unique")
    ]


class DocuwarePaymentMode(models.Model):
    _name = "docuware.payment.mode"

    name = fields.Char(required=True)
    payment_mode_id = fields.Many2one(
        "account.payment.mode", required=True, company_dependent=True
    )
    backend_id = fields.Many2one("docuware.backend")

    _sql_constraints = [
        ("unique_name", "unique(name, backend_id)", "name should be unique")
    ]
