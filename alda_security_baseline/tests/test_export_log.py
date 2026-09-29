# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import config

from ..models.alda_security_export_log import RETENTION_PARAM

EXPORTER_PASSWORD = "bl_exporter_pwd_1234"


class ExportLogCommon:
    @classmethod
    def _setup_export_data(cls):
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.Log = cls.env["alda.security.export.log"]
        group_user = cls.env.ref("base.group_user")
        Users = cls.env["res.users"]
        cls.exporter = Users.create(
            {
                "name": "Baseline Exporter",
                "login": "bl_exporter",
                "password": EXPORTER_PASSWORD,
                "groups_id": [
                    Command.link(group_user.id),
                    Command.link(cls.env.ref("base.group_allow_export").id),
                ],
            }
        )
        cls.plain = Users.create(
            {
                "name": "Baseline Plain",
                "login": "bl_plain",
                "groups_id": [Command.link(group_user.id)],
            }
        )
        cls.admin = Users.create(
            {
                "name": "Baseline Admin",
                "login": "bl_admin",
                "groups_id": [
                    Command.link(group_user.id),
                    Command.link(cls.env.ref("base.group_system").id),
                ],
            }
        )
        cls.partners = cls.env["res.partner"].create(
            [
                {"name": "Baseline Company", "is_company": True},
                {"name": "Baseline Person 1"},
                {"name": "Baseline Person 2"},
            ]
        )

    def _logs(self, user):
        return self.Log.search([("user_id", "=", user.id)])


@tagged("post_install", "-at_install")
class TestExportLog(ExportLogCommon, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_export_data()

    def test_export_is_logged(self):
        res = self.partners.with_user(self.exporter).export_data(["name", "email"])
        self.assertEqual(len(res["datas"]), 3)
        log = self._logs(self.exporter)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.model_name, "res.partner")
        self.assertEqual(log.record_count, 3)
        self.assertEqual(log.field_count, 2)
        self.assertFalse(log.import_compat)
        self.assertTrue(log.export_date)
        # Outside an HTTP request, every call is a row of its own.
        self.partners[:1].with_user(self.exporter).export_data(["name"])
        self.assertEqual(len(self._logs(self.exporter)), 2)

    def test_import_compat_is_logged(self):
        self.partners.with_user(self.exporter).with_context(
            import_compat=True
        ).export_data(["name"])
        self.assertTrue(self._logs(self.exporter).import_compat)

    def test_denied_export_is_not_logged(self):
        with self.assertRaises(UserError):
            self.partners.with_user(self.plain).export_data(["name"])
        self.assertFalse(self._logs(self.plain))

    def test_logging_failure_does_not_break_export(self):
        cr = self.env.cr

        def broken_create(*args, **kwargs):
            cr.execute(
                "SELECT * FROM alda_baseline_missing_table", log_exceptions=False
            )

        with patch.object(type(self.Log), "create", broken_create):
            with self.assertLogs(
                "odoo.addons.alda_security_baseline.models.base", level="ERROR"
            ):
                res = self.partners.with_user(self.exporter).export_data(["name"])
        self.assertEqual(len(res["datas"]), 3)
        # The transaction is still usable.
        self.assertFalse(self._logs(self.exporter))
        self.partners[:1].with_user(self.exporter).export_data(["name"])
        self.assertEqual(len(self._logs(self.exporter)), 1)

    def test_access_rights(self):
        self.partners.with_user(self.exporter).export_data(["name"])
        self.env.invalidate_all()
        for user in (self.plain, self.exporter):
            with self.assertRaises(AccessError):
                self.Log.with_user(user).check_access_rights("read")
            with self.assertRaises(AccessError):
                self.Log.with_user(user).search([])
        admin_logs = self.Log.with_user(self.admin).search(
            [("user_id", "=", self.exporter.id)]
        )
        self.assertEqual(len(admin_logs), 1)
        self.assertEqual(admin_logs.model_name, "res.partner")
        for mode in ("write", "create", "unlink"):
            self.assertFalse(
                self.Log.with_user(self.admin).check_access_rights(
                    mode, raise_exception=False
                )
            )

    def test_retention(self):
        now = fields.Datetime.now()
        vals = {"user_id": self.exporter.id, "model_name": "res.partner"}
        old = self.Log.create(dict(vals, export_date=now - timedelta(days=200)))
        recent = self.Log.create(dict(vals, export_date=now - timedelta(days=10)))
        ICP = self.env["ir.config_parameter"]
        self.assertEqual(ICP.get_param(RETENTION_PARAM), "180")
        self.Log._gc_export_logs()
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        ICP.set_param(RETENTION_PARAM, "0")
        self.Log._gc_export_logs()
        self.assertTrue(recent.exists())
        ICP.set_param(RETENTION_PARAM, "not a number")
        self.Log._gc_export_logs()
        self.assertTrue(recent.exists())
        ICP.set_param(RETENTION_PARAM, "5")
        self.Log._gc_export_logs()
        self.assertFalse(recent.exists())


@tagged("post_install", "-at_install")
class TestExportLogHttp(ExportLogCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_export_data()

    def setUp(self):
        super().setUp()
        # A host-based dbfilter (e.g. "^%d$") rejects the test server host.
        patcher = patch.dict(config.options, {"dbfilter": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _export(self, fmt, **params):
        data = {
            "model": "res.partner",
            "fields": [{"name": "name", "label": "Name"}],
            "ids": False,
            "domain": [("id", "in", self.partners.ids)],
            "groupby": [],
            "import_compat": False,
            "context": {},
        }
        data.update(params)
        response = self.url_open(
            "/web/export/%s" % fmt,
            data={
                "data": json.dumps(data),
                "csrf_token": http.Request.csrf_token(self),
            },
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_csv_export(self):
        self.authenticate("bl_exporter", EXPORTER_PASSWORD)
        self._export("csv", import_compat=True)
        log = self._logs(self.exporter)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.record_count, 3)
        self.assertTrue(log.import_compat)

    def test_grouped_xlsx_export_is_one_row(self):
        self.authenticate("bl_exporter", EXPORTER_PASSWORD)
        self._export("xlsx", groupby=["is_company"])
        log = self._logs(self.exporter)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.record_count, 3)
        self.assertEqual(log.field_count, 1)
        self.assertFalse(log.import_compat)
