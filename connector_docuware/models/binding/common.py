# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models

from odoo.addons.connector.exception import RetryableJobError


class DocuwareBinding(models.AbstractModel):
    _name = "docuware.binding"
    _inherit = "external.binding"
    _description = "docuware Binding (abstract)"

    # 'odoo_id': openerp-side id must be declared in concrete model
    backend_id = fields.Many2one(
        comodel_name="docuware.backend",
        string="docuware Backend",
        required=True,
        ondelete="restrict",
    )
    active = fields.Boolean(string="Active", default=True)
    docuware_id = fields.Char("ID on docuware")

    _sql_constraints = [
        (
            "docuware_uniq",
            "unique(backend_id, docuware_id)",
            "A record with same ID on docuware already exists.",
        ),
    ]

    def check_active(self, backend):
        if not backend.active:
            raise RetryableJobError(
                "Backend %s is inactive please consider changing this"
                "The job will be retried later." % (backend.name,)
            )

    @api.model
    def import_record(self, backend, docuware_id, force=False):
        """Import a record from docuware"""
        self.check_active(backend)
        with backend.work_on(self._name) as work:
            importer = work.component(usage="record.importer")
            return importer.run(docuware_id, force=force)

    @api.model
    def import_batch(self, backend, **kwargs):
        """Prepare a batch import of records from docuware"""
        self.check_active(backend)
        with backend.work_on(self._name) as work:
            importer = work.component(usage="batch.importer")
            return importer.run(**kwargs)

    def export_record(self, fields=None):
        """Export a record on docuware"""
        self.ensure_one()
        self.check_active(self.backend_id)
        with self.backend_id.work_on(self._name) as work:
            exporter = work.component(usage="record.exporter")
            return exporter.run(self, fields)

    def export_delete_record(self, backend, external_id, attributes=None):
        """Delete a record on docuware"""
        self.check_active(backend)
        with backend.work_on(self._name) as work:
            deleter = work.component(usage="record.exporter.deleter")
            return deleter.run(external_id, attributes)

    # TODO: Research
    def resync(self):
        func = self.import_record
        if self.env.context.get("connector_delay"):
            func = self.with_delay(priority=5).import_record
        for record in self:
            func(record.backend_id, record.docuware_id)
        return True


class DocuwareBindingOdoo(models.AbstractModel):
    _name = "docuware.binding.odoo"
    _inherit = "docuware.binding"
    _description = "docuware Binding with Odoo binding (abstract)"

    # 'odoo_id': odoo-side id must be re-declared in concrete model
    # for having a many2one instead of a reference field
    odoo_id = fields.Integer(
        string="Odoo binding"
    )

    _sql_constraints = [
        (
            "docuware_erp_uniq",
            "unique(backend_id, odoo_id)",
            "An ERP record with same ID already exists on docuware.",
        ),
    ]
