# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import threading
from contextlib import closing, contextmanager

import odoo

from odoo.addons.component.core import AbstractComponent
from odoo.addons.queue_job.exception import RetryableJobError

_logger = logging.getLogger(__name__)

RETRY_ON_ADVISORY_LOCK = 1  # seconds
RETRY_WHEN_CONCURRENT_DETECTED = 1  # seconds


def import_record():
    pass


def import_batch():
    pass


class DocuwareBaseImporter(AbstractComponent):
    _name = "docuware.base.importer"
    _inherit = ["base.importer", "base.docuware.connector"]


class DocuwareImporter(AbstractComponent):
    """Base importer for Docuware"""

    _name = "docuware.importer"
    _inherit = "docuware.base.importer"
    _usage = "record.importer"

    def __init__(self, environment):
        """
        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.ConnectorEnvironment`
        """
        super().__init__(environment)
        self.docuware_id = None
        self.docuware_record = None

    def _get_docuware_data(self):
        """Return the raw docuware data for ``self.docuware_id``"""
        return self.backend_adapter.read(self.docuware_id)

    def _has_to_skip(self, binding=False):
        """Return True if the import can be skipped"""
        return False

    def _import_dependencies(self):
        """Import the dependencies for the record"""
        return

    def _map_data(self):
        """Returns an instance of
        :py:class:`~odoo.addons.connector.unit.mapper.MapRecord`

        """
        return self.mapper.map_record(self.docuware_record)

    def _validate_data(self, data):
        """Check if the values to import are correct

        Pro-actively check before the ``Model.create`` or
        ``Model.update`` if some fields are missing

        Raise `InvalidDataError`
        """
        return

    def _get_binding(self):
        """Return the odoo id from the docuware id"""
        return self.binder.to_internal(self.docuware_id)

    def _context(self, **kwargs):
        return dict(self._context, connector_no_export=True, **kwargs)

    def _create_context(self):
        return {"connector_no_export": True}

    def _create_data(self, map_record):
        return map_record.values(for_create=True)

    def _update_data(self, map_record):
        return map_record.values()

    def _create(self, data):
        """Create the odoo record"""
        # special check on data before import
        self._validate_data(data)
        context = self._create_context()
        if data.get("pms_property_id"):
            context["default_pms_property_id"] = data.get("pms_property_id")
        if data.get("move_type"):
            context["default_move_type"] = data.get("move_type")
        if data.get("company_id"):
            context['allowed_company_ids'] = [data.get('company_id')]
        binding = self.model.with_context(context).create(data)
        _logger.debug("%d created from docuware %s", binding, self.docuware_id)
        return binding

    def _update(self, binding, data):
        """Update an odoo record"""
        # special check on data before import
        self._validate_data(data)
        binding.with_context(connector_no_export=True).write(data)
        _logger.debug("%d updated from docuware %s", binding, self.docuware_id)
        return

    def _before_import(self):
        """Hook called before the import, when we have the docuware
        data"""
        return

    def _after_import(self, binding):
        """Hook called at the end of the import"""
        return

    @contextmanager
    def do_in_new_connector_env(self, model_name=None):
        """Context manager that yields a new connector environment

        Using a new Odoo Environment thus a new PG transaction.

        This can be used to make a preemptive check in a new transaction,
        for instance to see if another transaction already made the work.
        """
        with odoo.api.Environment.manage():
            registry = odoo.modules.registry.Registry(self.env.cr.dbname)
            with closing(registry.cursor()) as cr:
                try:
                    new_env = odoo.api.Environment(cr, self.env.uid, self.env.context)
                    # connector_env = self.connector_env.create_environment(
                    #     self.backend_record.with_env(new_env),
                    #     model_name or self.model._name,
                    #     connector_env=self.connector_env
                    # )
                    with self.backend_record.with_env(new_env).work_on(
                        self.model._name
                    ) as work2:
                        yield work2
                except BaseException:
                    cr.rollback()
                    raise
                else:
                    # Despite what pylint says, this a perfectly valid
                    # commit (in a new cursor). Disable the warning.
                    self.env[
                        "base"
                    ].flush()  # TODO FIXME check if and why flush is mandatory here
                    if not getattr(threading.currentThread(), "testing", False):
                        cr.commit()  # pylint: disable=invalid-commit

    def _check_in_new_connector_env(self):
        # with self.do_in_new_connector_env() as new_connector_env:
        with self.do_in_new_connector_env():
            # Even when we use an advisory lock, we may have
            # concurrent issues.
            # Explanation:
            # We import Partner A and B, both of them import a
            # partner category X.
            #
            # The squares represent the duration of the advisory
            # lock, the transactions starts and ends on the
            # beginnings and endings of the 'Import Partner'
            # blocks.
            # T1 and T2 are the transactions.
            #
            # ---Time--->
            # > T1 /------------------------\
            # > T1 | Import Partner A       |
            # > T1 \------------------------/
            # > T1        /-----------------\
            # > T1        | Imp. Category X |
            # > T1        \-----------------/
            #                     > T2 /------------------------\
            #                     > T2 | Import Partner B       |
            #                     > T2 \------------------------/
            #                     > T2        /-----------------\
            #                     > T2        | Imp. Category X |
            #                     > T2        \-----------------/
            #
            # As you can see, the locks for Category X do not
            # overlap, and the transaction T2 starts before the
            # commit of T1. So no lock prevents T2 to import the
            # category X and T2 does not see that T1 already
            # imported it.
            #
            # The workaround is to open a new DB transaction at the
            # beginning of each import (e.g. at the beginning of
            # "Imp. Category X") and to check if the record has been
            # imported meanwhile. If it has been imported, we raise
            # a Retryable error so T2 is rollbacked and retried
            # later (and the new T3 will be aware of the category X
            # from the its inception).
            binder = self.binder_for(model=self.model._name)
            # binder = new_connector_env.get_connector_unit(Binder)
            if binder.to_internal(self.docuware_id):
                raise RetryableJobError(
                    "Concurrent error. The job will be retried later",
                    seconds=RETRY_WHEN_CONCURRENT_DETECTED,
                    ignore_retry=True,
                )

    def run(self, docuware_id, **kwargs):
        """Run the synchronization

        :param docuware_id: identifier of the record on docuware
        """
        self.docuware_id = docuware_id
        lock_name = "import({}, {}, {}, {})".format(
            self.backend_record._name,
            self.backend_record.id,
            self.model._name,
            self.docuware_id,
        )
        # Keep a lock on this import until the transaction is committed
        self.advisory_lock_or_retry(lock_name, retry_seconds=RETRY_ON_ADVISORY_LOCK)
        if not self.docuware_record:
            self.docuware_record = self._get_docuware_data()
        binding = self._get_binding()
        if not binding:
            self._check_in_new_connector_env()

        skip = self._has_to_skip(binding=binding)
        if skip:
            return skip

        # import the missing linked resources
        self._import_dependencies()

        self._import(binding, **kwargs)

    def _import(self, binding, **kwargs):
        """Import the external record.

        Can be inherited to modify for instance the session
        (change current user, values in context, ...)

        """

        map_record = self._map_data()

        if binding:
            record = self._update_data(map_record)
        else:
            record = self._create_data(map_record)

        # special check on data before import
        self._validate_data(record)

        if binding:
            self._update(binding, record)
        else:
            binding = self._create(record)

        self.binder.bind(self.docuware_id, binding)

        self._after_import(binding)


class BatchImporter(AbstractComponent):
    """The role of a BatchImporter is to search for a list of
    items to import, then it can either import them directly or delay
    the import of each item separately.
    """

    _name = "docuware.batch.importer"
    _inherit = ["base.importer", "base.docuware.connector"]
    _usage = "batch.importer"

    def run(self, filters=None, **kwargs):
        """Run the synchronization"""
        if filters is None:
            filters = {}
        record_ids = self.backend_adapter.search(filters)
        for record_id in record_ids:
            self._import_record(record_id, **kwargs)

    def _import_record(self, record):
        """Import a record directly or delay the import of the record"""
        raise NotImplementedError


class DirectBatchImporter(AbstractComponent):
    """Import the docuware Shop Groups + Shops

    They are imported directly because this is a rare and fast operation,
    performed from the UI.
    """

    _name = "docuware.direct.batch.importer"
    _inherit = "docuware.batch.importer"
    _model_name = None

    def _import_record(self, external_id):
        """Import the record directly"""
        self.env[self.model._name].import_record(
            backend=self.backend_record, docuware_id=external_id
        )


class DelayedBatchImporter(AbstractComponent):
    """Delay import of the records"""

    _name = "docuware.delayed.batch.importer"
    _inherit = "docuware.batch.importer"
    _model_name = None

    def _import_record(self, external_id, **kwargs):
        """Delay the import of the records"""
        priority = kwargs.pop("priority", None)
        eta = kwargs.pop("eta", None)
        max_retries = kwargs.pop("max_retries", None)
        description = kwargs.pop("description", None)
        channel = kwargs.pop("channel", None)
        identity_key = kwargs.pop("identity_key", None)

        self.env[self.model._name].with_delay(
            priority=priority,
            eta=eta,
            max_retries=max_retries,
            description=description,
            channel=channel,
            identity_key=identity_key,
        ).import_record(backend=self.backend_record, docuware_id=external_id, **kwargs)
