# Copyright 2019  Pablo Q. Barriuso
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class QueueJob(models.Model):
    _inherit = 'queue.job'


    def _message_post_on_failure(self):
        """
        Override this method to send a message to the user when the job fails.
        """
        migration_jobs = self.filtered(lambda job: job.model_name != 'migrated.hotel')
        super(QueueJob, migration_jobs)._message_post_on_failure()
