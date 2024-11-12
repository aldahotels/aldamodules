# Copyright 2019  Pablo Q. Barriuso
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import datetime
import json
import logging
import uuid
import traceback
import urllib.error
from itertools import groupby


import odoorpc.odoo

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, float_compare

_logger = logging.getLogger(__name__)


class MigratedHotel(models.Model):
    _name = "migrated.hotel"

    name = fields.Char("Name", copy=False)
    odoo_host = fields.Char("Host", help="Full URL to the host.")
    odoo_db = fields.Char("Database Name", required=True, help="Odoo database name.")
    odoo_user = fields.Char("Username", required=True, help="Odoo administration user.")
    odoo_password = fields.Char("Password", required=True, help="Odoo password.")
    odoo_port = fields.Integer(
        string="TCP Port",
        required=True,
        default=443,
        help="Specify the TCP port for the XML-RPC protocol.",
    )
    odoo_protocol = fields.Selection(
        [("jsonrpc+ssl", "jsonrpc+ssl")],
        "Protocol",
        required=True,
        default="jsonrpc+ssl",
    )
    odoo_version = fields.Char()

    migration_date_from = fields.Date("Migration date from (included)", copy=False)
    migration_date_to = fields.Date("Migration date to (included)", copy=False)

    log_ids = fields.One2many("migrated.log", "migrated_hotel_id")

    pms_property_id = fields.Many2one(
        string="Property",
        help="The migration property",
        comodel_name="pms.property",
        copy=False,
    )
    company_id = fields.Many2one(
        string="Company",
        related="pms_property_id.company_id",
        comodel_name="res.company",
        copy=False,
        readonly=True,
    )

    count_total_partners = fields.Integer(
        string="Partners Total V11", readonly=True, copy=False
    )
    count_migrated_partners = fields.Integer(
        string="Partners V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_partners = fields.Integer(
        string="Partners Tarjet (With documents)", readonly=True, copy=False
    )
    complete_partners = fields.Boolean(
        "Partners Complete",
        compute="_compute_complete_partners",
        store=True,
        copy=False,
    )

    count_total_folios = fields.Integer(
        string="Folios Total V11", readonly=True, copy=False
    )
    count_migrated_folios = fields.Integer(
        string="Folios V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_folios = fields.Integer(
        string="Folios Tarjet ('Migration D-Date')", readonly=True, copy=False
    )

    count_total_reservations = fields.Integer(
        string="Reservations Total V11", readonly=True, copy=False
    )
    count_migrated_reservations = fields.Integer(
        string="Reservations V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_reservations = fields.Integer(
        string="Reservations Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    complete_reservations = fields.Boolean(
        "Reservations Complete",
        compute="_compute_complete_reservations",
        store=True,
        copy=False,
    )

    count_total_checkins = fields.Integer(
        string="Checkins Total V11", readonly=True, copy=False
    )
    count_migrated_checkins = fields.Integer(
        string="Checkins V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_checkins = fields.Integer(
        string="Checkins Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    complete_checkins = fields.Boolean(
        "Checkins Complete",
        compute="_compute_complete_checkins",
        store=True,
        copy=False,
    )

    count_total_payments = fields.Integer(
        string="Payments Total V11", readonly=True, copy=False
    )
    count_migrated_payments = fields.Integer(
        string="Payments V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_payments = fields.Integer(
        string="Payments Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    count_total_invoices = fields.Integer(
        string="Invoices Total V11", readonly=True, copy=False
    )
    count_migrated_invoices = fields.Integer(
        string="Invoices V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_invoices = fields.Integer(
        string="Invoices Tarjet ('Migration D-Date')", readonly=True, copy=False
    )

    backend_id = fields.Many2one("channel.wubook.backend", copy=False)
    wubook_journal_id = fields.Many2one(
        "account.journal",
        string="Wubook Journal",
        copy=False,
    )
    wubook_parity_pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Wubook Parity Pricelist",
    )
    wubook_restriccion_plan_id = fields.Many2one(
        "pms.availability.plan",
        string="Wubook Restriction Plan",
    )
    dummy_closure_reason_id = fields.Many2one(
        string="Default Clousure Reasen", comodel_name="room.closure.reason"
    )
    dummy_product_id = fields.Many2one(
        string="Default Product", comodel_name="product.product"
    )
    default_channel_agency_id = fields.Many2one(
        string="Default agencys Channel", comodel_name="pms.sale.channel"
    )
    default_plan_avail_id = fields.Many2one("pms.availability.plan")
    folio_prefix = fields.Char("Add prefix on folios")
    default_ota_channel = fields.Many2one(
        string="Default OTAs Channel", comodel_name="pms.sale.channel"
    )
    booking_agency = fields.Many2one(
        string="Booking.com partner",
        comodel_name="res.partner",
        domain=[("is_agency", "=", True)],
    )
    expedia_agency = fields.Many2one(
        string="Expedia partner",
        comodel_name="res.partner",
        domain=[("is_agency", "=", True)],
    )
    hotelbeds_agency = fields.Many2one(
        string="HotelBeds partner",
        comodel_name="res.partner",
        domain=[("is_agency", "=", True)],
    )
    thinkin_agency = fields.Many2one(
        string="Thinkin partner",
        comodel_name="res.partner",
        domain=[("is_agency", "=", True)],
    )
    sh360_agency = fields.Many2one(
        string="SH360 partner",
        comodel_name="res.partner",
        domain=[("is_agency", "=", True)],
    )

    migrated_pricelist_ids = fields.One2many(
        string="Pricelists Mapping",
        readonly=False,
        comodel_name="migrated.pricelist",
        inverse_name="migrated_hotel_id",
    )
    count_total_pricelists = fields.Integer(
        string="Total Pricelists V11", readonly=True, copy=False
    )
    count_migrated_pricelists = fields.Integer(
        string="Pricelists V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_pricelists = fields.Integer(
        string="Pricelists Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    complete_pricelists = fields.Boolean(
        "Pricelists Complete",
        compute="_compute_complete_pricelists",
        store=True,
        copy=False,
    )

    migrated_room_type_ids = fields.One2many(
        string="Room Types Mapping",
        readonly=False,
        comodel_name="migrated.room.type",
        inverse_name="migrated_hotel_id",
    )
    count_total_room_types = fields.Integer(
        string="Total Room Types V11", readonly=True, copy=False
    )
    count_migrated_room_types = fields.Integer(
        string="Room Types V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_room_types = fields.Integer(
        string="Room Types Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    migrated_room_type_class_ids = fields.One2many(
        string="Room Type Clases Mapping",
        readonly=False,
        comodel_name="migrated.room.type.class",
        inverse_name="migrated_hotel_id",
    )
    auto_create_rooms = fields.Boolean(
        string="Create Rooms automatically", default=False, copy=False
    )
    migrated_room_ids = fields.One2many(
        string="Rooms Mapping",
        readonly=False,
        comodel_name="migrated.room",
        inverse_name="migrated_hotel_id",
    )
    count_total_rooms = fields.Integer(
        string="Total Rooms V11", readonly=True, copy=False
    )
    count_migrated_rooms = fields.Integer(
        string="Rooms V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_rooms = fields.Integer(
        string="Rooms Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    complete_rooms = fields.Boolean(
        "Rooms Complete", compute="_compute_complete_rooms", store=True, copy=False
    )
    auto_create_products = fields.Boolean(
        string="Create Products automatically", default=False, copy=False
    )
    migrated_product_ids = fields.One2many(
        string="Products Mapping",
        readonly=False,
        comodel_name="migrated.product",
        inverse_name="migrated_hotel_id",
    )
    count_total_products = fields.Integer(
        string="Total Products V11", readonly=True, copy=False
    )
    count_migrated_products = fields.Integer(
        string="Products V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_products = fields.Integer(
        string="Products Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    complete_products = fields.Boolean(
        "Products Complete",
        compute="_compute_complete_products",
        store=True,
        copy=False,
    )
    migrated_board_service_ids = fields.One2many(
        string="Boards Mapping",
        readonly=False,
        comodel_name="migrated.board.service",
        inverse_name="migrated_hotel_id",
    )
    count_total_board_services = fields.Integer(
        string="Total Boards V11", readonly=True, copy=False
    )
    count_migrated_board_services = fields.Integer(
        string="Boards V14 Migrated", readonly=True, copy=False
    )
    count_tarjet_board_services = fields.Integer(
        string="Boards Tarjet ('Migration D-Date')", readonly=True, copy=False
    )
    complete_boards = fields.Boolean(
        "Boards Complete", compute="_compute_complete_boards", store=True, copy=False
    )
    auto_create_board_service_room_types = fields.Boolean(
        string="Create Board Service in Room Types automatically",
        default=False,
        copy=False,
    )
    migrated_board_service_room_type_ids = fields.One2many(
        string="Board Rooms Services Mapping",
        readonly=False,
        comodel_name="migrated.board.service.room.type",
        inverse_name="migrated_hotel_id",
    )

    migrated_journal_ids = fields.One2many(
        string="Pricelists Mapping",
        readonly=False,
        comodel_name="migrated.journal",
        inverse_name="migrated_hotel_id",
    )
    count_total_journals = fields.Integer(
        string="Total Journals V11", readonly=True, copy=False
    )
    count_migrated_journals = fields.Integer(
        string="Journals V14 Migrated", readonly=True, copy=False
    )
    complete_journals = fields.Boolean(
        "Journals Complete",
        compute="_compute_complete_journals",
        store=True,
        copy=False,
    )

    migrated_channel_type_ids = fields.One2many(
        string="Channels Services Mapping",
        readonly=False,
        comodel_name="migrated.channel.type",
        inverse_name="migrated_hotel_id",
    )
    complete_channels = fields.Boolean(
        "Channels Complete",
        compute="_compute_complete_channels",
        store=True,
        copy=False,
    )
    next_step = fields.Selection(
        [
            ("0", "Preconfiguration"),
            ("1", "Create bindings"),
            ("2", "Import Prices and Rules from V2"),
            ("3", "Import Last folios"),
            ("4", "Import Last Payments"),
            ("5", "Import Last Payment returns"),
            ("6", "Import Last Invoices"),
            ("7", "Update create_uid&create_date"),
            ("8", "Go to Live"),
            ("9", "In live!"),
        ],
        string="Next Step",
        compute="_compute_next_step",
        inverse="_inverse_next_step",
        store=False,
    )
    step = fields.Integer(
        string="Step",
        default=0,
        copy=False,
    )

    last_import_rooms = fields.Datetime("Updated Rooms", copy=False)
    last_import_pricelists = fields.Datetime("Updated Pricelists", copy=False)
    last_import_partners = fields.Datetime("Updated Partners", copy=False)
    last_import_folios = fields.Datetime("Updated Folios", copy=False)
    last_import_payments = fields.Datetime("Updated Payments", copy=False)
    last_import_invoices = fields.Datetime("Updated Invoices", copy=False)
    last_import_products = fields.Datetime("Updated Products", copy=False)
    last_import_board_services = fields.Datetime("Updated BoardServices", copy=False)
    last_created_jobs_datetime = fields.Datetime("Last Created Jobs", copy=False)
    complete_folios = fields.Boolean(
        "Folios Complete", compute="_compute_completed_migration_folios"
    )
    count_total_job_folios = fields.Integer(
        string="Total Jobs Folios", compute="_compute_completed_migration_folios"
    )
    count_pending_job_folios = fields.Integer(
        string="Pending Jobs Folios", compute="_compute_completed_migration_folios"
    )
    count_failed_job_folios = fields.Integer(
        string="Failed Jobs Folios", compute="_compute_completed_migration_folios"
    )
    complete_payments = fields.Boolean(
        "Payments Complete", compute="_compute_completed_migration_payments"
    )
    count_total_job_payments = fields.Integer(
        string="Total Jobs Payments", compute="_compute_completed_migration_payments"
    )
    count_pending_job_payments = fields.Integer(
        string="Pending Jobs Payments", compute="_compute_completed_migration_payments"
    )
    count_failed_job_payments = fields.Integer(
        string="Failed Jobs Payments", compute="_compute_completed_migration_payments"
    )
    complete_returns = fields.Boolean(
        "Returns Complete", compute="_compute_completed_returns"
    )
    count_total_job_returns = fields.Integer(
        string="Total Jobs Returns", compute="_compute_completed_returns"
    )
    count_pending_job_returns = fields.Integer(
        string="Pending Jobs Returns", compute="_compute_completed_returns"
    )
    count_failed_job_returns = fields.Integer(
        string="Failed Jobs Returns", compute="_compute_completed_returns"
    )
    complete_invoices = fields.Boolean(
        "Invoices Complete", compute="_compute_completed_migration_invoices"
    )
    count_total_job_invoices = fields.Integer(
        string="Total Jobs Invoices", compute="_compute_completed_migration_invoices"
    )
    count_pending_job_invoices = fields.Integer(
        string="Pending Jobs Invoices", compute="_compute_completed_migration_invoices"
    )
    count_failed_job_invoices = fields.Integer(
        string="Failed Jobs Invoices", compute="_compute_completed_migration_invoices"
    )

    in_live = fields.Boolean(
        "In Live",
        compute="_compute_in_live",
    )

    folio_remote_name = fields.Char("Folio Remote Name", copy=False)

    @api.depends("count_tarjet_partners", "count_migrated_partners")
    def _compute_complete_partners(self):
        for record in self:
            if record.count_tarjet_partners == record.count_migrated_partners:
                record.complete_partners = True
            else:
                record.complete_partners = False

    @api.depends("count_total_reservations", "count_migrated_reservations")
    def _compute_complete_reservations(self):
        for record in self:
            if record.count_total_reservations == record.count_migrated_reservations:
                record.complete_reservations = True
            else:
                record.complete_reservations = False

    @api.depends("count_total_checkins", "count_migrated_checkins")
    def _compute_complete_checkins(self):
        for record in self:
            if record.count_total_checkins == record.count_migrated_checkins:
                record.complete_checkins = True
            else:
                record.complete_checkins = False


    @api.depends(
        "count_tarjet_pricelists",
        "count_migrated_pricelists",
        "migrated_pricelist_ids",
        "migrated_pricelist_ids.pms_pricelist_id",
    )
    def _compute_complete_pricelists(self):
        for record in self:
            if (
                record.count_total_pricelists == record.count_migrated_pricelists
                and all(x.pms_pricelist_id for x in record.migrated_pricelist_ids)
            ):
                record.complete_pricelists = True
            else:
                record.complete_pricelists = False

    @api.depends(
        "count_migrated_rooms", "migrated_room_ids", "migrated_room_ids.pms_room_id"
    )
    def _compute_complete_rooms(self):
        for record in self:
            if record.count_total_rooms == record.count_migrated_rooms and all(
                x.pms_room_id for x in record.migrated_room_ids
            ):
                record.complete_rooms = True
            else:
                record.complete_rooms = False

    @api.depends(
        "count_tarjet_products",
        "count_migrated_products",
        "migrated_product_ids",
        "migrated_product_ids.product_id",
    )
    def _compute_complete_products(self):
        for record in self:
            if record.count_migrated_products > 1 and all(
                x.product_id for x in record.migrated_product_ids
            ):
                record.complete_products = True
            else:
                record.complete_products = False

    @api.depends(
        "count_migrated_board_services",
        "migrated_board_service_room_type_ids",
        "migrated_board_service_room_type_ids.board_service_room_type_id",
    )
    def _compute_complete_boards(self):
        for record in self:
            if (
                record.count_total_board_services
                == record.count_migrated_board_services
                and all(
                    x.board_service_room_type_id
                    for x in record.migrated_board_service_room_type_ids
                )
            ):
                record.complete_boards = True
            else:
                record.complete_boards = False

    @api.depends(
        "count_migrated_journals",
        "migrated_journal_ids",
        "migrated_journal_ids.account_journal_id",
    )
    def _compute_complete_journals(self):
        for record in self:
            if record.count_migrated_journals > 0 and any(
                x.account_journal_id for x in record.migrated_journal_ids
            ):
                record.complete_journals = True
            else:
                record.complete_journals = False

    @api.depends(
        "migrated_channel_type_ids",
        "migrated_channel_type_ids",
        "migrated_channel_type_ids.channel_type_id",
    )
    def _compute_complete_channels(self):
        for record in self:
            if len(record.migrated_channel_type_ids) == 9 and all(
                x.channel_type_id for x in record.migrated_channel_type_ids
            ):
                record.complete_channels = True
            else:
                record.complete_channels = False

    def _compute_in_live(self):
        for record in self:
            if record.backend_id and not record.backend_id.parent_id.export_disabled:
                record.in_live = True
            else:
                record.in_live = False

    def count_remote_date(self):
        if (
            self.odoo_db
            and self.odoo_host
            and self.odoo_port
            and self.odoo_protocol
            and self.odoo_user
            and self.odoo_version
            and self.odoo_password
            and self.migration_date_from
            and self.migration_date_to
        ):
            try:
                noderpc = odoorpc.ODOO(
                    self.odoo_host, self.odoo_protocol, self.odoo_port
                )
                noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
            except (
                odoorpc.error.RPCError,
                odoorpc.error.InternalError,
                urllib.error.URLError,
            ) as err:
                raise ValidationError(err)
            self.count_total_pricelists = noderpc.env["product.pricelist"].search_count(
                ["|", ("active", "=", True), ("active", "=", False)]
            )
            self.count_total_room_types = noderpc.env["hotel.room.type"].search_count(
                ["|", ("active", "=", True), ("active", "=", False)]
            )
            self.count_total_rooms = noderpc.env["hotel.room"].search_count(
                ["|", ("active", "=", True), ("active", "=", False)]
            )
            self.count_total_board_services = noderpc.env[
                "hotel.board.service.room.type"
            ].search_count([])
            self.count_total_journals = noderpc.env["account.journal"].search_count([])
            self.count_total_products = noderpc.env["product.product"].search_count(
                ["|", ("active", "=", True), ("active", "=", False)]
            )
            self.count_total_partners = noderpc.env["res.partner"].search_count([])
            self.count_total_folios = noderpc.env["hotel.folio"].search_count([])
            self.count_total_reservations = noderpc.env[
                "hotel.reservation"
            ].search_count([])
            self.count_total_checkins = noderpc.env[
                "hotel.checkin.partner"
            ].search_count([])
            self.count_total_payments = noderpc.env["account.payment"].search_count([])
            self.count_total_invoices = noderpc.env["account.invoice"].search_count([])

            self.count_migrated_pricelists = len(self.migrated_pricelist_ids)
            self.count_migrated_room_types = len(self.migrated_room_type_ids)
            self.count_migrated_rooms = len(self.migrated_room_ids)
            self.count_migrated_board_services = len(
                self.migrated_board_service_room_type_ids
            )
            self.count_migrated_journals = len(self.migrated_journal_ids)
            self.count_migrated_products = len(self.migrated_product_ids)
            self.count_migrated_folios = self.env["pms.folio"].search_count(
                [
                    ("remote_id", "!=", False),
                    ("pms_property_id", "=", self.pms_property_id.id),
                ]
            )
            self.count_migrated_reservations = self.env["pms.reservation"].search_count(
                [
                    ("remote_id", "!=", False),
                    ("pms_property_id", "=", self.pms_property_id.id),
                ]
            )
            self.count_migrated_checkins = self.env["pms.checkin.partner"].search_count(
                [
                    ("remote_id", "!=", False),
                    ("pms_property_id", "=", self.pms_property_id.id),
                ]
            )
            # self.count_migrated_payments = self.env[""].search_count([("remote_id", "!=", False), ("pms_property_id", "=", self.pms_property_id.id)])
            # self.count_migrated_invoices = self.env[""].search_count([("remote_id", "!=", False), ("pms_property_id", "=", self.pms_property_id.id)])

            self.count_tarjet_pricelists = noderpc.env[
                "product.pricelist"
            ].search_count([])
            self.count_tarjet_room_types = noderpc.env["hotel.room.type"].search_count(
                []
            )
            self.count_tarjet_rooms = noderpc.env["hotel.room"].search_count([])
            self.count_tarjet_board_services = noderpc.env[
                "hotel.board.service.room.type"
            ].search_count([])
            self.count_tarjet_products = (
                noderpc.env["product.product"].search_count([])
                - self.count_tarjet_room_types
            )
            self.count_tarjet_partners = noderpc.env["res.partner"].search_count(
                [
                    "|",
                    ("vat", "!=", False),
                    ("document_number", "!=", False),
                ]
            )
            self.count_tarjet_folios = noderpc.env["hotel.folio"].search_count(
                [
                    (
                        "write_date",
                        ">=",
                        self.migration_date_from.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                    (
                        "write_date",
                        "<=",
                        self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                    "|",
                    ("room_lines", "!=", False),
                    ("service_ids", "!=", False),
                ]
            )
            self.count_tarjet_reservations = noderpc.env[
                "hotel.reservation"
            ].search_count(
                [
                    (
                        "write_date",
                        ">=",
                        self.migration_date_from.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                    (
                        "write_date",
                        "<=",
                        self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                ]
            )
            self.count_tarjet_checkins = noderpc.env[
                "hotel.checkin.partner"
            ].search_count(
                [
                    (
                        "write_date",
                        ">=",
                        self.migration_date_from.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                    (
                        "write_date",
                        "<=",
                        self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                ]
            )
            self.count_tarjet_payments = noderpc.env["account.payment"].search_count(
                [
                    (
                        "write_date",
                        ">=",
                        self.migration_date_from.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                    (
                        "write_date",
                        "<=",
                        self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                ]
            )
            self.count_tarjet_invoices = noderpc.env["account.invoice"].search_count(
                [
                    (
                        "write_date",
                        ">=",
                        self.migration_date_from.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                    (
                        "write_date",
                        "<=",
                        self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                ]
            )

    @api.model
    def create(self, vals):
        try:
            noderpc = odoorpc.ODOO(
                vals["odoo_host"], vals["odoo_protocol"], vals["odoo_port"]
            )
            noderpc.login(vals["odoo_db"], vals["odoo_user"], vals["odoo_password"])

            vals.update({"odoo_version": noderpc.version})

        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        else:
            hotel_id = super().create(vals)
            noderpc.logout()
            return hotel_id

    # PARTNERS ---------------------------------------------------------------------------------------------------------------------------

    def check_vat(self, vat, country_id):
        res_partner = self.env["res.partner"]
        # quick and partial off-line checksum validation
        check_func = res_partner.simple_vat_check
        # check with country code as prefix of the TIN
        vat_country, vat_number = res_partner._split_vat(vat)
        if not check_func(vat_country, vat_number):
            # if fails, check with country code from country
            country_code = self.env["res.country"].browse(country_id).code
            if country_code:
                if not check_func(country_code.lower(), vat):
                    return False
            else:
                return False
        return True

    def _prepare_partner_remote_data(
        self,
        rpc_res_partner,
        country_map_ids,
        country_state_map_ids,
        category_map_ids,
        document_data,
        ine_codes,
    ):
        # prepare country_id related field
        country_id = False
        state_id = False
        remote_id = rpc_res_partner["country_id"] and rpc_res_partner["country_id"][0]
        if remote_id:
            country_id = remote_id and country_map_ids.get(remote_id) or None
        elif rpc_res_partner["code_ine_id"] and rpc_res_partner["code_ine_id"][0]:
            ine_code = next(
                item
                for item in ine_codes
                if item["id"] == rpc_res_partner["code_ine_id"][0]
            )["code"]
            if "ES" in ine_code:
                country_id = self.env["res.country"].search([("code", "=", "ES")]).id
                state_id = (
                    self.env["res.country.state"]
                    .search([("ine_code", "=", ine_code)])
                    .id
                )
            else:
                country_id = (
                    self.env["res.country"].search([("code_alpha3", "=", ine_code)]).id
                )

        # prepare state_id related field
        if not state_id:
            remote_id = rpc_res_partner["state_id"] and rpc_res_partner["state_id"][0]
            state_id = remote_id and country_state_map_ids.get(remote_id) or None
        # prepare category_ids related field
        remote_ids = rpc_res_partner["category_id"] and rpc_res_partner["category_id"]
        category_ids = (
            remote_ids and [category_map_ids.get(str(r)) for r in remote_ids] or None
        )
        # prepare parent_id related field
        parent_id = rpc_res_partner["parent_id"]
        vat = rpc_res_partner["vat"]
        if parent_id:
            parent_id = (
                self.env["migrated.partner"]
                .search(
                    [
                        ("remote_id", "=", parent_id[0]),
                        ("migrated_hotel_id", "=", self.id),
                    ]
                )
                .id
            )
            vat = False

        comment = rpc_res_partner["comment"] or False
        # REVIEW: sin el prefijo del pais el check_vat lo da como NO valido, homogeneizar VATS????
        # if vat and not self.check_vat(vat, country_id):
        #     check_vat_msg = 'Invalid VAT number ' + vat + ' for this partner ' + rpc_res_partner['name']
        #     migrated_log = self.env['migrated.log'].create({
        #         'name': check_vat_msg,
        #         'date_time': fields.Datetime.now(),
        #         'migrated_hotel_id': self.id,
        #         'model': 'partner',
        #         'remote_id': rpc_res_partner['id'],
        #     })
        #     _logger.warning('res.partner with ID remote: [%s] LOG #%s: (%s)',
        #                     rpc_res_partner['id'], migrated_log.id, check_vat_msg)
        #     comment = check_vat_msg + "\n" + comment
        #     vat = False

        # TODO: prepare child_ids related field
        vals = {
            "remote_id": rpc_res_partner["id"],
            "lastname": rpc_res_partner["lastname"],
            "firstname": rpc_res_partner["firstname"],
            "phone": rpc_res_partner["phone"],
            "mobile": rpc_res_partner["mobile"],
            "email": rpc_res_partner["email"],
            "website": rpc_res_partner["website"],
            "lang": rpc_res_partner["lang"],
            "is_company": rpc_res_partner["is_company"],
            "type": rpc_res_partner["type"],
            "street": rpc_res_partner["street"],
            "residence_street": rpc_res_partner["street"],
            "street2": rpc_res_partner["street2"],
            "residence_street2": rpc_res_partner["street2"],
            "is_agency": rpc_res_partner["is_tour_operator"],
            # 'zip_id': rpc_res_partner['zip_id'] and rpc_res_partner['zip_id'][0],
            "zip": rpc_res_partner["zip"],
            "city": rpc_res_partner["city"],
            "state_id": state_id,
            "residence_state_id": state_id,
            "country_id": country_id,
            "residence_country_id": country_id,
            "nationality_id": country_id,
            "comment": comment,
            "id_numbers": [(0, 0, document_data)] if document_data else False,
            "gender": rpc_res_partner["gender"],
            "birthdate_date": rpc_res_partner["birthdate_date"],
            "category_id": category_ids and [[6, False, category_ids]] or None,
            "parent_id": parent_id if parent_id else False,
            "sale_channel_id": self.default_channel_agency_id.id
            if rpc_res_partner["is_tour_operator"]
            else False,
        }
        if vat:
            vals["vat"] = vat
        return vals

    def action_migrate_partners(self):
        self.ensure_one()

        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        PartnersMigrated = self.env["migrated.partner"]
        # prepare ine_codes
        _logger.info("Mapping local with remote 'ine code' ids...")
        ine_codes = noderpc.env["code.ine"].search_read([], ["code"])

        # prepare res.country ids
        _logger.info("Mapping local with remote 'res.country' ids...")
        remote_ids = noderpc.env["res.country"].search([])
        remote_xml_ids = noderpc.env["res.country"].browse(remote_ids).get_external_id()
        country_map_ids = {}
        for key, value in remote_xml_ids.items():
            # Known Issue: res.country base.an, base.nt, base.tp, base.yu, base.zr are not
            # migrated from Odoo version 10 to version 11
            res_country_id = self.env["ir.model.data"].xmlid_to_res_id(value)
            country_map_ids.update({int(key): res_country_id})

        # prepare res.country.state ids
        _logger.info("Mapping local with remote 'res.country.state' ids...")
        remote_ids = noderpc.env["res.country.state"].search([])
        remote_xml_ids = (
            noderpc.env["res.country.state"].browse(remote_ids).get_external_id()
        )
        country_state_map_ids = {}
        for key, value in remote_xml_ids.items():
            res_country_state_id = self.env["ir.model.data"].xmlid_to_res_id(value)
            country_state_map_ids.update({int(key): res_country_state_id})

        # prepare res.partner.category ids
        _logger.info("Mapping local with remote 'res.partner.category' ids...")
        remote_ids = noderpc.env["res.partner.category"].search([])
        remote_records = noderpc.env["res.partner.category"].browse(remote_ids)
        category_map_ids = {}
        for record in remote_records:
            if record.parent_id:
                res_partner_category = self.env["res.partner.category"].search(
                    [
                        ("name", "=", record.name.lower()),
                        ("parent_id.name", "=", record.parent_id.name.lower()),
                    ]
                )
            else:
                res_partner_category = self.env["res.partner.category"].search(
                    [
                        ("name", "=", record.name.lower()),
                    ]
                )
            # if not res_partner_category:
            #     if record.parent_id:
            #         parent_category_id = self.env['res.partner.category'].search([('name', '=', record.name)])
            #         if not parent_category_id:
            #             parent = self.env['res.partner.category'].create({'name': record.parent_id.name})
            #         res_partner_category = self.env['res.partner.category'].create({
            #             'name': record.name,
            #             'parent_id': parent.id,
            #         })
            #     else:
            #         res_partner_category = self.env['res.partner.category'].create({'name': record.name})
            res_partner_category_id = res_partner_category[0].id
            category_map_ids.update({str(record.id): res_partner_category_id})

        # prepare partners of interest
        _logger.info("Preparing 'res.partners' of interest...")

        partners_migrated_remote_ids = []
        partners_migrated = PartnersMigrated.search(
            [("migrated_hotel_id", "=", self.id)]
        )
        if partners_migrated:
            partners_migrated_remote_ids = partners_migrated.mapped("remote_id")
        # First, import remote partners without contacts (parent_id is not set)

        _logger.info("Migrating 'res.partners' without parent_id...")
        import_datetime = fields.Datetime.now()
        remote_partners_ids = noderpc.env["res.partner"].search(
            [
                ("id", "not in", partners_migrated_remote_ids),
                ("parent_id", "=", False),
                ("user_ids", "=", False),
                # ("create_date", ">=", self.migration_date_from.strftime(DEFAULT_SERVER_DATE_FORMAT)),
                # ("create_date", "<=", self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT)),
                "|",
                ("active", "=", True),
                ("active", "=", False),
                "|",
                ("vat", "!=", False),
                ("document_number", "!=", False),
            ]
        )
        for sublist in self.chunks(remote_partners_ids, 500):
            self.with_company(
                self.pms_property_id.company_id
            ).with_delay().partner_batch(
                sublist,
                country_map_ids,
                country_state_map_ids,
                category_map_ids,
                ine_codes,
            )

        # Second, import remote partners with contacts (already created in the previous step)
        # TODO
        # _logger.info("Migrating 'res.partners' with parent_id...")
        # remote_partners = noderpc.env['res.partner'].search_read([
        #     ('id', 'not in', partners_migrated_remote_ids),
        #     ('parent_id', '!=', False),
        #     ('user_ids', '=', False),
        #     ('write_date', self.migration_date_operator, self.migration_date_d.strftime(DEFAULT_SERVER_DATE_FORMAT)),
        #     '|', ('active', '=', True), ('active', '=', False),
        # ], partner_remote_fields)
        # total_records = len(remote_partners)
        # count = 0
        # for remote_res_partner in remote_partners:
        #     _logger.info('(%s/%s) User #%s started migration of res.partner with remote ID: [%s]',
        #                 total_records, count, self._uid, remote_res_partner["id"])
        #     self.with_delay().migration_partner(remote_res_partner, country_map_ids, country_state_map_ids, category_map_ids)
        #     count += 1
        #     total_count += 1
        self.last_import_partners = import_datetime
        noderpc.logout()

    @api.model
    def partner_batch(
        self,
        sublist,
        country_map_ids,
        country_state_map_ids,
        category_map_ids,
        ine_codes,
    ):
        """
        Prepare partner Batch
        """
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        partner_remote_fields = [
            "id",
            "document_number",
            "document_type",
            "is_company",
            "is_tour_operator",
            "document_expedition_date",
            "vat",
            "country_id",
            "state_id",
            "category_id",
            "parent_id",
            "lastname",
            "firstname",
            "phone",
            "mobile",
            "email",
            "website",
            "lang",
            "type",
            "street",
            "street2",
            "zip",
            "code_ine_id",
            "city",
            "comment",
            "gender",
            "birthdate_date",
        ]
        remote_partners = noderpc.env["res.partner"].search_read(
            [
                ("id", "in", sublist),
            ],
            partner_remote_fields,
        )
        for remote_res_partner in remote_partners:
            self.with_company(
                self.pms_property_id.company_id
            ).with_delay().migration_partner(
                remote_res_partner,
                country_map_ids,
                country_state_map_ids,
                category_map_ids,
                ine_codes,
            )

        # self.last_import_partners = fields.Datetime.now()
        # self.count_migrated_partners = self.env["migrated.partner"].search_count([("migrated_hotel_id", "=", self.id)])
        noderpc.logout()

    @api.model
    def migration_partner(
        self,
        rpc_res_partner,
        country_map_ids,
        country_state_map_ids,
        category_map_ids,
        ine_codes,
    ):
        PartnersMigrated = self.env["migrated.partner"]
        is_company = rpc_res_partner["is_company"]
        is_ota = rpc_res_partner["is_tour_operator"]
        # search document number
        document_data = False
        migrated_res_partner = False
        if (
            rpc_res_partner["document_number"]
            and rpc_res_partner["document_type"]
            and not is_company
            and not is_ota
        ):
            category_id = (
                self.env["res.partner.id_category"]
                .search([("code", "=", rpc_res_partner["document_type"])])
                .id
            )
            partner_document = self.env["res.partner.id_number"].search(
                [
                    ("category_id", "=", category_id),
                    ("name", "=", rpc_res_partner["document_number"]),
                ]
            )
            if partner_document:
                migrated_res_partner = partner_document.partner_id
                PartnersMigrated.create(
                    {
                        "date_time": fields.Datetime.now(),
                        "migrated_hotel_id": self.id,
                        "remote_id": rpc_res_partner["id"],
                        "partner_id": partner_document.partner_id.id,
                    }
                )
            else:
                document_data = {
                    "category_id": category_id,
                    "name": rpc_res_partner["document_number"],
                    "valid_from": rpc_res_partner["document_expedition_date"],
                }
        if not migrated_res_partner and rpc_res_partner["vat"]:
            country_id = False
            remote_id = rpc_res_partner["country_id"] and rpc_res_partner["country_id"][0]
            if remote_id:
                country_id = remote_id and country_map_ids.get(remote_id) or None
            elif rpc_res_partner["code_ine_id"] and rpc_res_partner["code_ine_id"][0]:
                ine_code = next(
                    item
                    for item in ine_codes
                    if item["id"] == rpc_res_partner["code_ine_id"][0]
                )["code"]
                if "ES" in ine_code:
                    country_id = self.env["res.country"].search([("code", "=", "ES")]).id
                else:
                    country_id = (
                        self.env["res.country"].search([("code_alpha3", "=", ine_code)]).id
                    )
            if country_id and rpc_res_partner["vat"]:
                migrated_res_partner = self._get_partner_vat(country_id=country_id, vat=rpc_res_partner["vat"])
        if migrated_res_partner:
            _logger.info(
                "User #%s found with identity document: [%s]",
                rpc_res_partner["id"],
                rpc_res_partner["document_number"],
            )
            PartnersMigrated.create(
                {
                    "date_time": fields.Datetime.now(),
                    "migrated_hotel_id": self.id,
                    "remote_id": rpc_res_partner["id"],
                    "partner_id": migrated_res_partner.id,
                }
            )
        elif document_data or rpc_res_partner["vat"] and (is_company or is_ota):
            vals = self._prepare_partner_remote_data(
                rpc_res_partner,
                country_map_ids,
                country_state_map_ids,
                category_map_ids,
                document_data,
                ine_codes,
            )
            context_partner = {
                "tracking_disable": True,
                "mail_notrack": True,
                "mail_create_nolog": True,
                "id_no_validate": True,
                "avoid_document_restriction": True,
            }
            migrated_res_partner = (
                self.env["res.partner"].with_context(context_partner).create(vals)
            )
            migrated_res_partner.message_post(
                body=_(
                    """Migrated from: <b>%s</b> V2""",
                    self.pms_property_id.name,
                ),
                email_from=self.pms_property_id.partner_id.email_formatted,
            )
            PartnersMigrated.create(
                {
                    "date_time": fields.Datetime.now(),
                    "migrated_hotel_id": self.id,
                    "remote_id": rpc_res_partner["id"],
                    "partner_id": migrated_res_partner.id,
                }
            )
            _logger.info(
                "User #%s migrated res.partner with ID [local, remote]: %s",
                migrated_res_partner.id,
                rpc_res_partner["id"],
            )
        else:
            PartnersMigrated.create(
                {
                    "date_time": fields.Datetime.now(),
                    "migrated_hotel_id": self.id,
                    "remote_id": rpc_res_partner["id"],
                    "partner_id": False,
                }
            )
            _logger.info(
                "Partner without documentation: [%s] (not migrated)",
                rpc_res_partner["id"],
            )

    # FOLIOS ---------------------------------------------------------------------------------------------------------------------------

    def _prepare_folio_remote_data(
        self,
        rpc_hotel_folio,
        res_users_map_ids,
        category_map_ids,
        reservations_folio,
        reservation_lines_folio,
        services_folio,
        service_lines_folio,
        remote_checkin_partners,
        remote_bindings,
    ):
        # search res_partner id
        remote_id = rpc_hotel_folio["partner_id"] and rpc_hotel_folio["partner_id"][0]
        res_partner = (
            self.env["migrated.partner"]
            .search(
                [
                    ("remote_id", "=", remote_id),
                    ("migrated_hotel_id", "=", self.id),
                ]
            )
            .partner_id
            or False
        )
        partner_mobile = False
        partner_email = False
        if not res_partner:
            if rpc_hotel_folio["reservation_type"] == "out":
                partner_name = self.dummy_closure_reason_id.name
            # REVIEW: if partner not found, search name??
            else:
                partner_name = rpc_hotel_folio["partner_id"][1]
                partner_email = rpc_hotel_folio["email"]
                partner_mobile = (
                    rpc_hotel_folio["mobile"]
                    if rpc_hotel_folio["mobile"]
                    else rpc_hotel_folio["phone"]
                )
        else:
            partner_name = res_partner.name
            partner_email = res_partner.email
            partner_mobile = (
                res_partner.mobile if res_partner.mobile else res_partner.phone
            )

        # search res_partner invoice id
        res_partner_invoice_id = False
        remote_id = (
            rpc_hotel_folio["partner_invoice_id"]
            and rpc_hotel_folio["partner_invoice_id"][0]
        )
        res_partner_invoice = (
            self.env["migrated.partner"]
            .search(
                [
                    ("remote_id", "=", remote_id),
                    ("migrated_hotel_id", "=", self.id),
                ]
            )
            .partner_id
        )
        if res_partner_invoice:
            res_partner_invoice_id = res_partner_invoice.id
        else:
            if res_partner:
                res_partner_invoice_id = res_partner.id
            else:
                # REVIEW: Atención! Sería una factura simplificada pero en la migración no se debería dar este caso en un folio facturado
                res_partner_invoice_id = False

        # search res_users ids
        remote_id = rpc_hotel_folio["user_id"] and rpc_hotel_folio["user_id"][0]
        res_user_id = remote_id and res_users_map_ids.get(str(remote_id))
        remote_id = rpc_hotel_folio["create_uid"] and rpc_hotel_folio["create_uid"][0]
        res_create_uid = remote_id and res_users_map_ids.get(str(remote_id))
        # prepare category_ids related field
        remote_ids = (
            rpc_hotel_folio["segmentation_ids"] and rpc_hotel_folio["segmentation_ids"]
        )
        category_ids = (
            remote_ids and [category_map_ids.get(str(r)) for r in remote_ids] or False
        )

        # Prepare pricelist
        remote_id = rpc_hotel_folio["pricelist_id"][0]
        pricelist_id = (
            self.env["migrated.pricelist"]
            .search(
                [("remote_id", "=", remote_id), ("migrated_hotel_id", "=", self.id)]
            )
            .pms_pricelist_id.id
        )

        # prepare default state value
        state = "confirm"
        if rpc_hotel_folio["state"] != "sale":
            state = rpc_hotel_folio["state"]

        # Prepare service in folio without reservation assigned
        services_vals = False
        if rpc_hotel_folio["service_ids"]:
            remote_services = [
                ser for ser in services_folio if not ser["ser_room_line"]
            ]
            for remote_service in remote_services:
                remote_service_lines = [
                    line
                    for line in service_lines_folio
                    if line["service_id"] == remote_service["id"]
                ]
                services_vals = [
                    (
                        0,
                        0,
                        self._prepare_migrate_services(
                            remote_service, remote_service_lines
                        ),
                    )
                ]

        vals = {
            "remote_id": rpc_hotel_folio["id"],
            "name": self.folio_prefix + rpc_hotel_folio["name"],
            "partner_name": partner_name,
            "mobile": partner_mobile,
            "email": partner_email,
            "pricelist_id": pricelist_id,
            "service_ids": services_vals,
            "segmentation_ids": category_ids and [[6, False, category_ids]] or False,
            "reservation_type": rpc_hotel_folio["reservation_type"],
            # TODO: Mover a reservations: 'internal_comment': rpc_hotel_folio['customer_notes'],
            "internal_comment": rpc_hotel_folio["internal_comment"],
            "state": state,
            "cancelled_reason": rpc_hotel_folio["cancelled_reason"],
            "date_order": rpc_hotel_folio["date_order"],
            "confirmation_date": rpc_hotel_folio["confirmation_date"],
            "create_date": rpc_hotel_folio["create_date"],
            "pms_property_id": self.pms_property_id.id,
            "user_id": res_user_id,
            "create_uid": res_create_uid,
        }
        if res_partner:
            vals.update(
                {
                    "partner_id": res_partner.id,
                    "partner_invoice_ids": [(4, res_partner_invoice_id)],
                }
            )
        if rpc_hotel_folio["reservation_type"] == "out":
            vals.update({"closure_reason_id": self.dummy_closure_reason_id.id})

        if rpc_hotel_folio["room_lines"]:
            reservations_vals = self._prepare_folio_reservations(
                reservations_folio,
                reservation_lines_folio,
                services_folio,
                service_lines_folio,
                remote_checkin_partners,
                res_users_map_ids,
                rpc_hotel_folio['customer_notes'],
            )
            vals.update({"reservation_ids": reservations_vals})

        # Prepare channel and binding
        # Wubook
        wubook_reservation = False
        for reservation in reservations_folio:
            if reservation["external_id"]:
                wubook_reservation = reservation
                break
        if wubook_reservation:
            binding = [
                b
                for b in remote_bindings
                if b["external_id"] == wubook_reservation["external_id"]
            ][0]
            remote_ota_id = (
                wubook_reservation["ota_id"] and wubook_reservation["ota_id"][1] or None
            )
            if remote_ota_id:
                vals["sale_channel_origin_id"] = self.default_ota_channel.id
                if remote_ota_id == "Booking.com":
                    vals["agency_id"] = self.booking_agency.id
                if remote_ota_id == "Expedia":
                    vals["agency_id"] = self.expedia_agency.id
                if remote_ota_id == "HotelBeds":
                    vals["agency_id"] = self.hotelbeds_agency.id
            else:
                vals["sale_channel_origin_id"] = self.backend_id.parent_id.backend_type_id.child_id.direct_channel_type_id.id
            binding_vals = {
                "backend_id": self.backend_id.id,
                "external_id": binding["external_id"],
                "wubook_status": binding["channel_status"],
            }
            vals.update({"channel_wubook_bind_ids": [(0, False, binding_vals)]})
        # Not Wubook
        else:
            remote_id = (
                rpc_hotel_folio["tour_operator_id"]
                and rpc_hotel_folio["tour_operator_id"][0]
            )
            agency = (
                remote_id
                and self.env["migrated.partner"]
                .search(
                    [
                        ("remote_id", "=", remote_id),
                        ("migrated_hotel_id", "=", self.id),
                    ]
                )
                .partner_id
            )
            res_create = self.env["res.users"].browse(res_create_uid)
            if remote_id:
                vals["agency_id"] = agency.id
                vals["sale_channel_origin_id"] = agency.sale_channel_id.id
            elif "@thinkin.es" in res_create.login:
                vals["agency_id"] = self.thinkin_agency.id
                vals["sale_channel_origin_id"] = self.thinkin_agency.sale_channel_id.id
            elif "@sh360.es" in res_create.login:
                vals["agency_id"] = self.sh360_agency.id
                vals["sale_channel_origin_id"] = self.sh360_agency.sale_channel_id.id
            else:
                vals["agency_id"] = False
                vals["sale_channel_origin_id"] = (
                    self.env["migrated.channel.type"]
                    .search(
                        [
                            ("remote_name", "=", rpc_hotel_folio["channel_type"]),
                            ("migrated_hotel_id", "=", self.id),
                        ]
                    )
                    .channel_type_id.id
                )

        return vals

    def action_migrate_folio(self):
        self.ensure_one()
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        try:
            for pricelist in self.env["migrated.pricelist"].search([("migrated_hotel_id", "=", self.id)]).mapped("pms_pricelist_id"):
                if pricelist.pms_property_ids and self.pms_property_id not in pricelist.pms_property_ids:
                    pricelist.pms_property_ids = [(4, self.pms_property_id.id)]
            remote_name = self.folio_remote_name
            folio_remote_id = noderpc.env["hotel.folio"].search(
                [("name", "=", remote_name)]
            )
            if not folio_remote_id:
                raise ValidationError(
                    _("There is no folio with name '%s'") % remote_name
                )
            else:
                self.action_migrate_folios(remote_folio_ids=[folio_remote_id[0]])
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        else:
            noderpc.logout()

    def action_migrate_folios(self, remote_folio_ids=False, final=False):
        self.ensure_one()
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        try:
            # 0- Review pms_property_ids config
            _logger.info("Reviewing pms_property_ids config")
            for pricelist in self.env["migrated.pricelist"].search([("migrated_hotel_id", "=", self.id)]).mapped("pms_pricelist_id"):
                if pricelist.pms_property_ids and self.pms_property_id not in pricelist.pms_property_ids:
                    pricelist.pms_property_ids = [(4, self.pms_property_id.id)]
            for product in self.env["migrated.product"].search([("migrated_hotel_id", "=", self.id)]).mapped("product_id"):
                if product.pms_property_ids and self.pms_property_id not in product.pms_property_ids:
                    product.pms_property_ids = [(4, self.pms_property_id.id)]
            for room_type in self.env["migrated.room.type"].search([("migrated_hotel_id", "=", self.id)]).mapped("pms_room_type_id"):
                if room_type.pms_property_ids and self.pms_property_id not in room_type.pms_property_ids:
                    room_type.pms_property_ids = [(4, self.pms_property_id.id)]
            # prepare res.users ids
            _logger.info("Mapping local with remote 'res.users' ids...")
            remote_ids = noderpc.env["res.users"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            remote_records = noderpc.env["res.users"].browse(remote_ids)
            res_users_map_ids = {}
            for record in remote_records:
                if record.login in ["default", "portaltemplate", "public"]:
                    continue
                res_user = (
                    self.env["res.users"]
                    .sudo()
                    .search(
                        [
                            ("login", "=", record.login),
                            "|",
                            ("active", "=", True),
                            ("active", "=", False),
                        ]
                    )
                )
                if record.id == 1:
                    res_user = self.backend_id.parent_id.user_id
                    if not res_user:
                        raise ValidationError(
                            _("The user of the parent backend is not set.")
                        )
                if not res_user:
                    new_partner = (
                        self.env["res.partner"]
                        .sudo()
                        .create(
                            {
                                "name": record.name,
                                "email": record.email,
                            }
                        )
                    )
                    context = {
                        "tracking_disable": True,
                        "mail_notrack": True,
                        "mail_create_nolog": True,
                        "id_no_validate": True,
                    }
                    res_user = (
                        self.env["res.users"]
                        .sudo()
                        .with_context(context)
                        .create(
                            {
                                "partner_id": new_partner.id,
                                "email": record.email,
                                "login": record.login,
                                "company_ids": [
                                    (4, self.pms_property_id.company_id.id)
                                ],
                                "company_id": self.pms_property_id.company_id.id,
                                "pms_property_ids": [(4, self.pms_property_id.id)],
                                "pms_property_id": self.pms_property_id.id,
                            }
                        )
                    )
                    res_user.active = False
                if self.pms_property_id.company_id.id not in res_user.company_ids.ids:
                    res_user.sudo().write(
                        {
                            "company_ids": [(4, self.pms_property_id.company_id.id)],
                        }
                    )
                if self.pms_property_id.id not in res_user.pms_property_ids.ids:
                    res_user.sudo().write(
                        {
                            "pms_property_ids": [(4, self.pms_property_id.id)],
                        }
                    )
                res_users_id = (
                    res_user.id if res_user else self._context.get("uid", self._uid)
                )
                res_users_map_ids.update({str(record.id): res_users_id})
            # prepare res.partner.category ids
            _logger.info("Mapping local with remote 'res.partner.category' ids...")
            remote_ids = noderpc.env["res.partner.category"].search([])
            remote_records = noderpc.env["res.partner.category"].browse(remote_ids)
            category_map_ids = {}
            for record in remote_records:
                if record.parent_id:
                    res_partner_category = self.env["res.partner.category"].search(
                        [
                            ("name", "=", record.name.lower()),
                            ("parent_id.name", "=", record.parent_id.name.lower()),
                        ]
                    )
                else:
                    res_partner_category = self.env["res.partner.category"].search(
                        [("name", "=", record.name.lower())]
                    )
                if res_partner_category:
                    category_map_ids.update({str(record.id): res_partner_category.id})
                # else:
                #     parent = False
                #     if record.parent_id:
                #         parent = self.env['res.partner.category'].create({'name': record.parent_id.name})
                #     res_partner_category = self.env['res.partner.category'].create({
                #         'name' : record.name,
                #         'parent_id': parent.id if parent else False,
                #     })
                #     category_map_ids.update({record.id: res_partner_category.id})

            # prepare folios of interest
            _logger.info("Preparing 'hotel.folio' of interest...")
            import_datetime = fields.Datetime.now()
            if not remote_folio_ids:
                if not final:
                    remote_hotel_reservation_ids = noderpc.env["hotel.reservation"].search(
                        [
                            (
                                "checkout",
                                ">=",
                                self.migration_date_from.strftime(
                                    DEFAULT_SERVER_DATE_FORMAT
                                ),
                            ),
                            (
                                "checkout",
                                "<=",
                                self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                            ),
                            ("is_automatic_blocked", "=", False),
                        ]
                    )
                else:
                    remote_hotel_reservation_ids = noderpc.env["hotel.reservation"].search(
                        [
                            (
                                "checkout",
                                ">=",
                                self.migration_date_to.strftime(
                                    DEFAULT_SERVER_DATE_FORMAT
                                ),
                            ),
                        ]
                    )
                remote_hotel_reservations = (
                    noderpc.env["hotel.reservation"].search_read(
                        [
                            ("id", "in", remote_hotel_reservation_ids),
                        ],
                        ["folio_id"],
                    )
                    or []
                )
                remote_hotel_folio_ids = noderpc.env["hotel.folio"].search(
                    [
                        (
                            "id",
                            "in",
                            list(
                                {
                                    res["folio_id"][0]
                                    for res in remote_hotel_reservations
                                }
                            ),
                        ),
                        "|",
                        ("room_lines", "!=", False),
                        ("service_ids", "!=", False),
                    ]
                )
                # PARTIR POR paquetes de 500?? y  recuperar el ultimo ID del paquete
                for sublist in self.chunks(remote_hotel_folio_ids, 500):
                    self.with_company(
                        self.pms_property_id.company_id
                    ).with_delay().folio_batch(
                        sublist, category_map_ids, res_users_map_ids,
                    )
                self.last_import_folios = import_datetime
            else:
                self.with_company(self.pms_property_id.company_id).folio_batch(
                    remote_folio_ids,
                    category_map_ids,
                    res_users_map_ids,
                    direct_import=True,
                )

        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        else:
            noderpc.logout()

    @api.model
    def folio_batch(
        self, sublist, category_map_ids, res_users_map_ids, direct_import=False
    ):
        """
        Prepare Folio batch
        """
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        remote_hotel_folios = (
            noderpc.env["hotel.folio"].search_read(
                [
                    ("id", "in", sublist),
                ],
                [
                    "id",
                    "name",
                    "partner_id",
                    "email",
                    "phone",
                    "mobile",
                    "pricelist_id",
                    "tour_operator_id",
                    "service_ids",
                    "segmentation_ids",
                    "reservation_type",
                    "channel_type",
                    "internal_comment",
                    "state",
                    "cancelled_reason",
                    "date_order",
                    "confirmation_date",
                    "create_date",
                    "user_id",
                    "create_uid",
                    "room_lines",
                    "partner_invoice_id",
                    "amount_total",
                    "customer_notes",
                ],
            )
            or []
        )
        _logger.info("%s Folios to migrate", len(remote_hotel_folios))

        _logger.info("Preparing 'hotel.reservation' of interest...")

        remote_hotel_reservations = (
            noderpc.env["hotel.reservation"].search_read(
                [
                    ("folio_id", "in", [fol["id"] for fol in remote_hotel_folios]),
                ],
                [
                    "id",
                    "folio_id",
                    "room_id",
                    "room_type_id",
                    "discount",
                    "checkin",
                    "checkout",
                    "arrival_hour",
                    "departure_hour",
                    "pricelist_id",
                    "board_service_room_id",
                    "to_assign",
                    "state",
                    "cancelled_reason",
                    "out_service_description",
                    "adults",
                    "children",
                    "splitted",
                    "parent_reservation",
                    "overbooking",
                    "channel_type",
                    "call_center",
                    "external_id",
                    "ota_id",
                    "reservation_line_ids",
                    "checkin_partner_ids",
                    "service_ids",
                    "create_uid",
                    "last_updated_res",
                    "ota_id",
                    "ota_reservation_id",
                ],
            )
            or []
        )
        # Reservation Bindings
        remote_bindings = noderpc.env["channel.hotel.reservation"].search_read(
            [
                ("odoo_id", "in", [res["id"] for res in remote_hotel_reservations]),
            ],
            [
                "id",
                "odoo_id",
                "ota_id",
                "ota_reservation_id",
                "channel_status",
                "external_id",
            ],
        )
        _logger.info("%s Reservations to migrate", len(remote_hotel_reservations))

        _logger.info("Preparing 'hotel.reservetion.line' of interest...")

        remote_hotel_reservation_lines = (
            noderpc.env["hotel.reservation.line"].search_read(
                [
                    (
                        "reservation_id",
                        "in",
                        [r["id"] for r in remote_hotel_reservations],
                    ),
                ],
                [
                    "id",
                    "reservation_id",
                    "room_id",
                    "date",
                    "discount",
                    "cancel_discount",
                    "price",
                ],
            )
            or []
        )

        _logger.info(
            "%s Reservation lines to migrate", len(remote_hotel_reservation_lines)
        )
        _logger.info("Preparing 'hotel.service' of interest...")

        remote_hotel_services = noderpc.env["hotel.service"].search_read(
            [
                "|",
                ("folio_id", "in", [folio["id"] for folio in remote_hotel_folios]),
                (
                    "ser_room_line",
                    "in",
                    [reservation["id"] for reservation in remote_hotel_reservations],
                ),
            ],
            [
                "id",
                "folio_id",
                "ser_room_line",
                "product_id",
                "name",
                "is_board_service",
                "discount",
                "channel_type",
                "service_line_ids",
                "create_date",
                "product_qty",
                "price_unit",
            ],
        )

        _logger.info("%s Services to migrate", len(remote_hotel_services))
        _logger.info("Preparing 'hotel.service.line' of interest...")

        remote_hotel_service_lines = noderpc.env["hotel.service.line"].search_read(
            [
                (
                    "service_id",
                    "in",
                    [service["id"] for service in remote_hotel_services],
                ),
            ],
            ["service_id", "date", "create_date", "day_qty", "price_unit"],
        )

        _logger.info("%s Service lines to migrate", len(remote_hotel_service_lines))
        _logger.info("Preparing 'hotel.checkin.partner' of interest...")

        remote_checkin_partners = noderpc.env["hotel.checkin.partner"].search_read(
            [("reservation_id", "in", [r["id"] for r in remote_hotel_reservations])],
            ["reservation_id", "partner_id", "enter_date", "exit_date", "state"],
        )
        _logger.info("%s Checkin partners to migrate", len(remote_checkin_partners))
        # TODO: Revisar Folios ya migrados
        # folios_migrated_remote_ids = []
        # folios_migrated = self.env["pms.folio"].search([("pms_property_id", "=", self.pms_property_id.id)])
        # if folios_migrated:
        #     folios_migrated_remote_ids = folios_migrated.mapped("remote_id")
        # remote_hotel_folio_ids = list(set(remote_hotel_folios) - set(folios_migrated_remote_ids))
        remote_folio_ids = (
            self.env["pms.folio"]
            .search([("pms_property_id", "=", self.pms_property_id.id)])
            .mapped("remote_id")
        )
        count = 0
        errors_count = 0
        total = len(remote_hotel_folios)
        _logger.info("Migrating 'hotel.folio'... Number of Folios: %s", total)
        for remote_hotel_folio in remote_hotel_folios:
            if remote_hotel_folio["id"] in remote_folio_ids:
                _logger.info("Folio %s already migrated", remote_hotel_folio["id"])
                continue
            _logger.info(
                "Started migration of hotel.folio with remote ID: [%s]",
                remote_hotel_folio,
            )
            reservations_folio = [
                res
                for res in remote_hotel_reservations
                if res["folio_id"][0] == remote_hotel_folio["id"]
            ]
            reservation_lines_folio = [
                res
                for res in remote_hotel_reservation_lines
                if res["reservation_id"][0]
                in [item["id"] for item in reservations_folio]
            ]
            services_folio = [
                res
                for res in remote_hotel_services
                if res["folio_id"][0] == remote_hotel_folio["id"]
            ]
            service_lines_folio = [
                res
                for res in remote_hotel_service_lines
                if res["service_id"][0] in [item["id"] for item in services_folio]
            ]
            checkins_partners_folio = [
                res
                for res in remote_checkin_partners
                if res["reservation_id"][0]
                in [item["id"] for item in reservations_folio]
            ]
            folio_remote_bindings = [
                b
                for b in remote_bindings
                if b["odoo_id"][0] in [item["id"] for item in reservations_folio]
            ]
            if not direct_import:
                self.with_company(
                    self.pms_property_id.company_id
                ).with_delay().migration_folio(
                    remote_hotel_folio,
                    res_users_map_ids,
                    category_map_ids,
                    reservations_folio,
                    reservation_lines_folio,
                    services_folio,
                    service_lines_folio,
                    checkins_partners_folio,
                    folio_remote_bindings,
                )
            else:
                self.with_company(self.pms_property_id.company_id).with_delay().migration_folio(
                    remote_hotel_folio,
                    res_users_map_ids,
                    category_map_ids,
                    reservations_folio,
                    reservation_lines_folio,
                    services_folio,
                    service_lines_folio,
                    checkins_partners_folio,
                    folio_remote_bindings,
                )
            count += 1
            _logger.info(
                "Finished migration of hotel.folio with remote ID: [%s]",
                remote_hotel_folio,
            )
            _logger.info("Migrated %s of %s hotel.folio", count, total)
            _logger.info("Errors: %s", errors_count)
            _logger.info(
                "=============================================================="
            )

        self.count_migrated_folios = self.env["pms.folio"].search_count(
            [
                ("remote_id", "!=", False),
                ("pms_property_id", "=", self.pms_property_id.id),
            ]
        )
        self.count_migrated_reservations = self.env["pms.reservation"].search_count(
            [
                ("remote_id", "!=", False),
                ("pms_property_id", "=", self.pms_property_id.id),
            ]
        )
        self.count_migrated_checkins = self.env["pms.checkin.partner"].search_count(
            [
                ("remote_id", "!=", False),
                ("pms_property_id", "=", self.pms_property_id.id),
            ]
        )
        noderpc.logout()

    @api.model
    def migration_folio(
        self,
        remote_hotel_folio,
        res_users_map_ids,
        category_map_ids,
        reservations,
        reservation_lines,
        services,
        service_lines,
        remote_checkin_partners,
        remote_bindings,
    ):
        vals = self._prepare_folio_remote_data(
            remote_hotel_folio,
            res_users_map_ids,
            category_map_ids,
            reservations,
            reservation_lines,
            services,
            service_lines,
            remote_checkin_partners,
            remote_bindings,
        )
        # disable mail feature to speed-up migration
        context_folio = {
            "tracking_disable": True,
            "mail_notrack": True,
            "mail_create_nolog": True,
            "connector_no_export": True,
            "id_no_validate": True,
        }
        new_folio = self.env["pms.folio"].with_context(context_folio).create(vals)
        new_folio.incongruence_data_migration = False
        if remote_hotel_folio["reservation_type"] == "normal":
            remote_amount = remote_hotel_folio["amount_total"]
            if (
                float_compare(remote_amount, new_folio.amount_total, precision_digits=2)
                != 0
            ):
                new_folio.incongruence_data_migration = True
        folio_note = self._get_folio_note(remote_hotel_folio)
        new_folio.message_post(
            body=folio_note,
            email_from=self.pms_property_id.partner_id.email_formatted,
        )
        for reservation in new_folio.reservation_ids:
            remote_res = [
                res for res in reservations if res["id"] == reservation.remote_id
            ]
            remote_res_lines = [
                res
                for res in reservation_lines
                if res["reservation_id"][0] == reservation.remote_id
            ]
            remote_services = []
            remote_services = [
                res
                for res in services
                if res["ser_room_line"]
                and res["ser_room_line"][0] == reservation.remote_id
            ]
            res_note = self._get_reservation_note(
                remote_res, remote_res_lines, remote_services
            )
            reservation.message_post(
                body=res_note,
                email_from=self.pms_property_id.partner_id.email_formatted,
            )

    # RESERVATIONS ---------------------------------------------------------------------------------------------------------------------------

    def _prepare_reservation_remote_data(
        self,
        reservation,
        reservation_lines,
        services,
        service_lines,
        remote_checkin_partners,
        res_users_map_ids,
        customer_notes=False,
    ):

        # prepare hotel_room_type related field
        remote_id = reservation["room_type_id"] and reservation["room_type_id"][0]
        room_type_id = (
            self.env["migrated.room.type"]
            .search(
                [("remote_id", "=", remote_id), ("migrated_hotel_id", "=", self.id)]
            )
            .pms_room_type_id.id
        )
        # prepare hotel_room related field
        remote_id = reservation["room_id"] and reservation["room_id"][0]
        preferred_room_id = (
            remote_id
            and self.env["migrated.room"]
            .search(
                [("remote_id", "=", remote_id), ("migrated_hotel_id", "=", self.id)]
            )
            .pms_room_id.id
        )
        # prepare channel_ota_info related field
        # remote_id = reservation['wchannel_id'] and reservation['wchannel_id'][0] or None
        # ota_id = remote_id and ota_map_ids.get(remote_id) or None

        # search res_users ids
        remote_id = reservation["create_uid"] and reservation["create_uid"][0]
        res_create_uid = remote_id and res_users_map_ids.get(str(remote_id))

        # Prepare pricelist
        remote_id = reservation["pricelist_id"][0]
        pricelist_id = (
            self.env["migrated.pricelist"]
            .search(
                [("remote_id", "=", remote_id), ("migrated_hotel_id", "=", self.id)]
            )
            .pms_pricelist_id.id
        )
        if not pricelist_id:
            ValidationError("Pricelist not found for remote id: %s" % remote_id)

        # prepare checkins
        remote_ids = (
            reservation["checkin_partner_ids"] and reservation["checkin_partner_ids"]
        )
        hotel_checkin_partners = [
            checkin
            for checkin in remote_checkin_partners
            if checkin["id"] in remote_ids
        ]
        checkins_cmds = []

        for hotel_checkin in hotel_checkin_partners[: reservation["adults"]]:
            partner_id = (
                self.env["migrated.partner"]
                .search(
                    [
                        ("remote_id", "=", hotel_checkin["partner_id"][0]),
                        ("migrated_hotel_id", "=", self.id),
                    ]
                )
                .partner_id.id
            )
            state = hotel_checkin["state"]
            if state == "booking":
                state = "onboard"
            if state == "cancelled":
                state = "cancel"

            checkins_cmds.append(
                (
                    0,
                    False,
                    {
                        "partner_id": partner_id,
                        "arrival": fields.Date.from_string(
                            hotel_checkin["enter_date"]
                        ).strftime(DEFAULT_SERVER_DATE_FORMAT),
                        "departure": fields.Date.from_string(
                            hotel_checkin["exit_date"]
                        ).strftime(DEFAULT_SERVER_DATE_FORMAT),
                        "state": state,
                    },
                )
            )

        # Mapper Cancel state
        state = reservation["state"]
        if reservation["state"] == "cancelled":
            state = "cancel"
        elif reservation["state"] == "booking":
            state = "onboard"

        # prepare_reservation_lines
        remote_ids = (
            reservation["reservation_line_ids"] and reservation["reservation_line_ids"]
        )
        hotel_reservation_lines = [
            line for line in reservation_lines if line["id"] in remote_ids
        ]

        reservation_line_cmds = []
        for reservation_line in hotel_reservation_lines:
            room_line_id = (
                self.env["migrated.room"]
                .search(
                    [
                        ("remote_id", "=", reservation_line["room_id"][0]),
                        ("migrated_hotel_id", "=", self.id),
                    ]
                )
                .pms_room_id.id
            )
            price = reservation_line["price"]
            cancel_discount = reservation_line["cancel_discount"]
            discount = reservation_line["discount"]
            if price == 0:
                if reservation["state"] == "cancel":
                    cancel_discount = 100
                else:
                    discount = 100
            reservation_line_cmds.append(
                (
                    0,
                    False,
                    {
                        "date": reservation_line["date"],
                        "price": price,
                        "discount": discount,
                        "cancel_discount": cancel_discount,
                        "room_id": room_line_id,
                    },
                )
            )

        board_service = False
        if reservation["board_service_room_id"]:
            board_service = self.env["migrated.board.service.room.type"].search(
                [
                    ("remote_id", "=", reservation["board_service_room_id"][0]),
                    ("migrated_hotel_id", "=", self.id),
                ]
            )
        board_service_room_id = (
            board_service.board_service_room_type_id.id if board_service else False
        )

        # TODO 'splitted': reservation['splitted']
        # if reservation['parent_reservation']:
        #     parent_reservation_id = self.env['hotel.reservation'].search([
        #         ('remote_id', '=', reservation['parent_reservation'][0])
        #     ]).id or None
        #     vals.update({'parent_reservation': parent_reservation_id})

        # TODO 'call_center': reservation['call_center'],

        services_vals = []
        if reservation["service_ids"] and state != "cancel":
            remote_records = [
                service
                for service in services
                if service["id"] in reservation["service_ids"]
            ]
            for remote_service in remote_records:
                lines = [
                    line
                    for line in service_lines
                    if line["id"] in remote_service["service_line_ids"]
                ]
                services_vals.append(
                    (0, 0, self._prepare_migrate_services(remote_service, lines))
                )

        # prepare pms.folio.reservation_ids
        vals = {
            # folio_id': folio_id,
            "remote_id": reservation["id"],
            "room_type_id": room_type_id,
            "preferred_room_id": preferred_room_id,
            "checkin": fields.Date.from_string(reservation["checkin"]).strftime(
                DEFAULT_SERVER_DATE_FORMAT
            ),
            "checkout": fields.Date.from_string(reservation["checkout"]).strftime(
                DEFAULT_SERVER_DATE_FORMAT
            ),
            "arrival_hour": reservation["arrival_hour"],
            "departure_hour": reservation["departure_hour"],
            "board_service_room_id": board_service_room_id,
            # 'nights': reservation['nights'],
            "to_assign": reservation["to_assign"],
            # 'to_send': reservation['to_send'],
            "state": state,
            "pricelist_id": pricelist_id,
            "cancelled_reason": reservation["cancelled_reason"],
            "out_service_description": reservation["out_service_description"],
            "adults": reservation["adults"],
            "children": reservation["children"],
            "overbooking": reservation["overbooking"],
            "service_ids": services_vals if services_vals else False,
            "reservation_line_ids": reservation_line_cmds,
            "create_uid": res_create_uid,
            "avoid_mails": True,
            "to_send_confirmation_mail": False,
            "to_send_cancelation_mail": False,
            "to_send_modification_mail": False,
            "to_send_exit_mail": False,
            "ota_reservation_code": reservation["ota_reservation_id"],
            "partner_requests": customer_notes,
        }

        if len(checkins_cmds) > 0:
            vals["checkin_partner_ids"] = checkins_cmds

        return vals

    def _prepare_folio_reservations(
        self,
        reservations,
        reservation_lines,
        services,
        service_lines,
        remote_checkin_partners,
        res_users_map_ids,
        customer_notes=False,
    ):
        # TODO: OTAs de Booking como Agencias

        # prepare channel.ota.info ids
        # _logger.info("Mapping local with remote 'channel.ota.info' ids...")
        # remote_ids = noderpc.env['wubook.channel.info'].search([])
        # remote_records = noderpc.env['wubook.channel.info'].browse(remote_ids)
        # ota_map_ids = {}
        # for record in remote_records:
        #     res_ota_id = self.env['channel.ota.info'].search([
        #         ('ota_id', '=', int(record.wid)),
        #     ]).id
        #     ota_map_ids.update({record.id: res_ota_id})

        # prepare reservation of interest
        _logger.info("Preparing folio reservations")
        reservation_vals = [] if reservations else False
        for remote_hotel_reservation in reservations:
            # REVIEW: reservas ya migradas
            # migrated_hotel_reservation = self.env['pms.reservation'].search([
            #     ('remote_id', '=', remote_hotel_reservation_id),
            #     ('pms_property_id', '=', self.pms_property_id.id),
            # ]) or None

            # if not migrated_hotel_reservation:
            _logger.info(
                "User #%s started migration of hotel.reservation with remote ID: [%s]",
                self._uid,
                remote_hotel_reservation["id"],
            )
            lines = [
                line
                for line in reservation_lines
                if line["reservation_id"][0] == remote_hotel_reservation["id"]
            ]
            res_services = [
                service
                for service in services
                if service["ser_room_line"]
                and service["ser_room_line"][0] == remote_hotel_reservation["id"]
            ]
            res_service_lines = [
                ser_line
                for ser_line in service_lines
                if ser_line["service_id"][0]
                in [service["id"] for service in res_services]
            ]
            reservation_vals.append(
                (
                    0,
                    0,
                    self._prepare_reservation_remote_data(
                        # hotel_folio_id,
                        remote_hotel_reservation,
                        lines,
                        res_services,
                        res_service_lines,
                        remote_checkin_partners,
                        res_users_map_ids,
                        customer_notes,
                        # room_type_map_ids,
                        # room_map_ids,
                        # ota_map_ids,
                    ),
                )
            )
            # migrated_hotel_reservation = self.env['hotel.reservation'].with_context(context_no_mail).create(vals)

            # _logger.info('User #%s migrated hotel.reservation with ID [local, remote]: [%s, %s]',
            #              self._uid, migrated_hotel_reservation.id, remote_hotel_reservation_id)

        return reservation_vals

    # SERVICES ---------------------------------------------------------------------------------------------------------------------------

    def _prepare_migrate_services(self, remote_service, remote_service_lines):
        try:
            self.ensure_one()
            # Check product per_day
            remote_id = remote_service["product_id"][0]
            product = (
                self.env["migrated.product"]
                .search(
                    [
                        ("remote_id", "=", remote_id),
                        ("migrated_hotel_id", "=", self.id),
                    ]
                )
                .product_id
            )

            # Prepare service lines
            service_lines_cmds = False
            if len(remote_service_lines) > 0:
                service_lines_cmds = []
                for line in remote_service_lines:
                    date = line["date"]
                    if not date:
                        date = remote_service["create_date"]
                    date = fields.Date.from_string(date).strftime(
                        DEFAULT_SERVER_DATE_FORMAT
                    )
                    service_lines_cmds.append(
                        (
                            0,
                            0,
                            {
                                "date": date,
                                "day_qty": line["day_qty"],
                                "price_unit": line["price_unit"],
                            },
                        )
                    )
            else:
                service_lines_cmds = [
                    (
                        0,
                        0,
                        {
                            "date": remote_service["create_date"],
                            "day_qty": remote_service["product_qty"],
                            "price_unit": remote_service["price_unit"],
                        },
                    )
                ]

            service_vals = {
                "remote_id": remote_service["id"],
                "product_id": product.id if product else self.dummy_product_id.id,
                "per_day": product.per_day,
                "name": remote_service["name"],
                "discount": remote_service["discount"],
                "sale_channel_origin_id": remote_service["channel_type"],
                "is_board_service": remote_service["is_board_service"],
                "service_line_ids": service_lines_cmds,
                "no_auto_add_lines": True,
            }
            return service_vals
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

    # PAYMENTS ---------------------------------------------------------------------------------------------------------------------------

    def action_migrate_payments(self, final=False):
        self.ensure_one()
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        try:
            # Prepare Users
            _logger.info("Mapping local with remote 'res.users' ids...")
            remote_ids = noderpc.env["res.users"].search([])
            remote_records = noderpc.env["res.users"].browse(remote_ids)
            res_users_map_ids = {}
            for record in remote_records:
                res_users = self.env["res.users"].search(
                    [
                        ("login", "=", record.login),
                    ]
                )
                res_users_id = (
                    res_users.id if res_users else self._context.get("uid", self._uid)
                )
                res_users_map_ids.update({str(record.id): res_users_id})
            import_datetime = fields.Datetime.now()
            migrated_remote_folios_ids = self.env["pms.folio"].search(
                [
                    ("remote_id", "!=", False),
                    ("pms_property_id", "=", self.pms_property_id.id),
                ]
            ).ids
            if not final:
                domain = [
                    '|',
                    ('folio_id', 'in', migrated_remote_folios_ids),
                    '&',
                    (
                        "payment_date",
                        ">=",
                        self.migration_date_from.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                    (
                        "payment_date",
                        "<=",
                        self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                ]
            else:
                domain = [
                    '|',
                    ('folio_id', 'in', migrated_remote_folios_ids),
                    (
                        "payment_date",
                        ">=",
                        self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    ),
                ]
            payments_already_migrated_ids = self.env["account.payment"].search([
                ('remote_id', '!=', False),
                ('pms_property_id', '=', self.pms_property_id.id),
                '|',
                '|',
                ('partner_type', '!=', 'customer'),
                ('payment_type', '!=', 'outbound'),
                ('is_internal_transfer', '=', True),
            ]).mapped("remote_id")
            if payments_already_migrated_ids:
                domain.append(('id', 'not in', payments_already_migrated_ids))

            remote_payment_vals = noderpc.env["account.payment"].search_read(
                domain,
                [
                    "payment_type",
                    "partner_type",
                    "partner_id",
                    "amount",
                    "journal_id",
                    "destination_journal_id",
                    "payment_date",
                    "communication",
                    "folio_id",
                    "state",
                    "create_uid",
                ],
            )
            total = len(remote_payment_vals)
            _logger.info("Total Number of Payments: %s", total)
            self.with_company(
                self.pms_property_id.company_id
            ).with_delay().migration_payments(
                remote_payment_vals,
                res_users_map_ids,
            )
            self.last_import_payments = import_datetime
        except (ValueError, ValidationError, Exception) as err:
            traceback.print_exc()
            _logger.info("error: {}".format(err))
            migrated_log = self.env["migrated.log"].create(
                {
                    "name": err,
                    "date_time": fields.Datetime.now(),
                    "migrated_hotel_id": self.id,
                    "model": "payment",
                }
            )
            _logger.error(
                "ERROR account.payment with LOG #%s: (%s)", migrated_log.id, err
            )

    def migration_payments(self, remote_payment_vals, res_users_map_ids):
        try:
            # Funtion to group by journal
            def journal_func(k):
                return k["journal_id"]

            # Funtion to group by date
            def date_func(k):
                return k["payment_date"]

            total = len(remote_payment_vals)
            remote_payment_by_journal_vals = sorted(
                remote_payment_vals, key=journal_func
            )
            # prepare not imported folios
            folios_to_import_ids = []
            for payment in remote_payment_vals:
                if payment["folio_id"]:
                    folio = self.env["pms.folio"].search(
                        [
                            ("remote_id", "=", payment["folio_id"][0]),
                            ("pms_property_id", "=", self.pms_property_id.id),
                        ]
                    )
                    if not folio and payment["folio_id"][0] not in folios_to_import_ids:
                        folios_to_import_ids.append(payment["folio_id"][0])
            if folios_to_import_ids:
                self.action_migrate_folios(folios_to_import_ids)
            migrated_journals = []
            count = 0
            for remote_journal, journal_payments in groupby(
                remote_payment_by_journal_vals, journal_func
            ):
                if remote_journal[0] in migrated_journals:
                    continue
                journal_id = (
                    self.env["migrated.journal"]
                    .search(
                        [
                            ("migrated_hotel_id", "=", self.id),
                            ("remote_id", "=", remote_journal[0]),
                        ]
                    )
                    .account_journal_id.id
                )
                if not journal_id:
                    _logger.info("Journal No MAPPED: %s", remote_journal[1])
                    continue
                self.env["account.journal"].browse(journal_id)
                remote_journal_ids = (
                    self.env["migrated.journal"]
                    .search([("account_journal_id", "=", journal_id)])
                    .mapped("remote_id")
                )
                migrated_journals.extend(remote_journal_ids)
                journal_payments_tarjet = list(
                    filter(
                        lambda x: x["journal_id"][0] in remote_journal_ids,
                        remote_payment_vals,
                    )
                )
                journal_payments_tarjet = sorted(
                    journal_payments_tarjet, key=date_func
                )
                for payment in journal_payments_tarjet:
                    # Some payment are garbage, so we skip them (know by old dates)
                    if fields.Datetime.from_string(payment["payment_date"]) < (
                        datetime.datetime.now() - datetime.timedelta(days=2000)
                    ):
                        continue
                    self.with_company(
                        self.pms_property_id.company_id
                    ).with_delay().create_bank_payment_migration(
                        payment, remote_journal, res_users_map_ids, journal_id
                    )
                    count += 1
                    _logger.info(
                        "(%s/%s) Migrated account.payment with ID (remote): %s",
                        count,
                        total,
                        payment["id"],
                    )
                # Add payments internal transfer with same date and journal like destination journal
                destination_payment_vals = list(
                    filter(
                        lambda x: x["payment_type"] == "transfer"
                        and x["destination_journal_id"][0] == remote_journal[0],
                        journal_payments_tarjet,
                    )
                )
                for pay in destination_payment_vals:
                    _logger.info("Destination Journal Payments")
                    self.with_company(
                        self.pms_property_id.company_id
                    ).with_delay().create_bank_payment_migration(
                        payment, remote_journal, res_users_map_ids, journal_id
                    )
                    count += 1
                    _logger.info(
                        "(%s/%s) Migrated account.payment with ID (remote): %s",
                        count,
                        total,
                        payment["id"],
                    )
        except (ValueError, ValidationError, Exception) as err:
            traceback.print_exc()
            _logger.info("error: {}".format(err))
            migrated_log = self.env["migrated.log"].create(
                {
                    "name": err,
                    "date_time": fields.Datetime.now(),
                    "migrated_hotel_id": self.id,
                    "model": "payment",
                }
            )
            _logger.error(
                "ERROR account.payment with LOG #%s: (%s)", migrated_log.id, err
            )

    def create_bank_payment_migration(
        self, payment, remote_journal, res_users_map_ids, journal_id
    ):
        remote_id = payment["create_uid"] and payment["create_uid"][0]
        res_create_uid = remote_id and res_users_map_ids.get(str(remote_id))
        if payment["partner_id"]:
            partner_id = (
                self.env["migrated.partner"]
                .search(
                    [
                        ("remote_id", "=", payment["partner_id"][0]),
                        ("migrated_hotel_id", "=", self.id),
                    ]
                )
                .partner_id.id
                or False
            )
        else:
            partner_id = False
        payment_ref = payment["communication"]
        if not payment_ref:
            if payment["folio_id"]:
                payment_ref = payment["folio_id"][1]
            else:
                payment_ref = "Transaccion"
        remote_folio_id = payment["folio_id"] and payment["folio_id"][0]
        if remote_folio_id:
            folio_id = (
                self.env["pms.folio"]
                .search(
                    [
                        ("remote_id", "=", remote_folio_id),
                        ("pms_property_id", "=", self.pms_property_id.id),
                    ],
                    limit=1,
                )
                .id
                or False
            )
        else:
            folio_id = False

        payment_type = payment["payment_type"]
        is_internal_transfer = False
        destination_journal = False
        if payment_type == "transfer":
            is_internal_transfer = True
            destination_journal = (
                self.env["migrated.journal"]
                .search(
                    [
                        ("migrated_hotel_id", "=", self.id),
                        ("remote_id", "=", payment["destination_journal_id"][0]),
                    ]
                )
                .account_journal_id
            )
            partner_id = destination_journal.company_id.partner_id.id
            if payment["destination_journal_id"][0] == remote_journal[0]:
                payment_type = "inbound"
            elif payment["journal_id"][0] == remote_journal[0]:
                payment_type = "outbound"
        vals = {
            "journal_id": journal_id,
            "partner_id": partner_id,
            "amount": payment["amount"],
            "date": fields.Datetime.from_string(payment["payment_date"]),
            "ref": payment_ref,
            "payment_type": payment_type,
            "state": "draft",
            "create_uid": res_create_uid,
            "is_internal_transfer": is_internal_transfer,
            "remote_id": payment["id"],
        }
        if payment["partner_type"]:
            vals["partner_type"] = payment["partner_type"]
        if destination_journal and destination_journal.bank_account_id:
            vals["partner_bank_id"] = destination_journal.bank_account_id.id
        if folio_id:
            vals["folio_ids"] = [(6, 0, [folio_id])]
        context_no_mail = {
            "tracking_disable": True,
            "mail_notrack": True,
            "mail_create_nolog": True,
            "company_id": self.pms_property_id.company_id.id,
        }
        pay = self.env["account.payment"].with_context(context_no_mail).create(vals)
        pay.with_context(context_no_mail).action_post()

    # def _get_statements(self, statement, dates, journal_id):
    #     dates = list(set(dates))
    #     current_position = dates.index(statement.date)
    #     next_statement = False
    #     if current_position < (len(dates) - 1):
    #         next_statement = self.env["account.bank.statement"].search(
    #             [
    #                 ("date", "=", dates[current_position + 1]),
    #                 ("journal_id", "=", journal_id),
    #             ]
    #         )
    #         if next_statement:
    #             next_statement = next_statement[0]
    #     previus_statement = False
    #     if current_position > 1:
    #         previus_statement = self.env["account.bank.statement"].search(
    #             [
    #                 ("date", "=", dates[current_position - 1]),
    #                 ("journal_id", "=", journal_id),
    #             ]
    #         )
    #         if previus_statement:
    #             previus_statement = previus_statement[0]
    #     return next_statement, previus_statement

    # def recursive_statements_post(
    #     self, current_statement, next_statement, previus_statement, dates
    # ):
    #     current_statement.button_post()
    #     # statement.button_validate()
    #     if next_statement and next_statement.state == "draft":
    #         next_one_statement = self._get_statements(current_statement, dates)[0]
    #         self.recursive_statements_post(next_statement, next_one_statement, False)
    #     if previus_statement and previus_statement.state == "draft":
    #         previus_one_statement = self._get_statements(current_statement, dates)[1]
    #         self.recursive_statements_post(
    #             previus_statement, False, previus_one_statement
    #         )

    # def create_payment_migration(
    #     self, payment, res_users_map_ids, remote_journal, date_str, journal, statement
    # ):
    #     remote_id = payment["create_uid"] and payment["create_uid"][0]
    #     res_create_uid = remote_id and res_users_map_ids.get(str(remote_id))
    #     if payment["partner_id"]:
    #         partner_id = (
    #             self.env["migrated.partner"]
    #             .search(
    #                 [
    #                     ("remote_id", "=", payment["partner_id"][0]),
    #                     ("migrated_hotel_id", "=", self.id),
    #                 ]
    #             )
    #             .partner_id.id
    #             or False
    #         )
    #     else:
    #         partner_id = False
    #     remote_folio_id = payment["folio_id"] and payment["folio_id"][0]
    #     if remote_folio_id:
    #         folio_id = (
    #             self.env["pms.folio"]
    #             .search(
    #                 [
    #                     ("remote_id", "=", remote_folio_id),
    #                     ("pms_property_id", "=", self.pms_property_id.id),
    #                 ],
    #                 limit=1,
    #             )
    #             .id
    #             or False
    #         )
    #     else:
    #         folio_id = False
    #     payment_ref = payment["communication"]
    #     if not payment_ref:
    #         if payment["folio_id"]:
    #             payment_ref = payment["folio_id"][1]
    #         else:
    #             payment_ref = "Transaccion"

    #     # Check Payment
    #     if payment["payment_type"] == "inbound":
    #         amount = payment["amount"]
    #     elif payment["payment_type"] == "outbound":
    #         amount = -payment["amount"]
    #     elif payment["payment_type"] == "transfer":
    #         if payment["destination_journal_id"][0] == remote_journal[0]:
    #             amount = payment["amount"]
    #         elif payment["journal_id"][0] == remote_journal[0]:
    #             amount = -payment["amount"]
    #     vals = {
    #         "date": fields.Date.from_string(date_str).strftime(
    #             DEFAULT_SERVER_DATE_FORMAT
    #         ),
    #         "amount": amount,
    #         "partner_id": partner_id,
    #         "payment_ref": payment_ref,
    #         "journal_id": journal.id,
    #         "counterpart_account_id": journal.suspense_account_id.id,
    #         "statement_id": statement.id,
    #         "create_uid": res_create_uid,
    #         "remote_id": payment["id"],
    #     }
    #     if folio_id:
    #         vals["folio_ids"] = [(6, 0, [folio_id])]
    #     self.env["account.bank.statement.line"].create(vals)
    #     return amount

    def action_migrate_payment_returns(self):
        self.ensure_one()
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        try:
            _logger.info("Preparing 'payment.return' of interest...")
            migrated_payments_remote_ids = self.env["account.payment"].search([
                ('remote_id', '!=', False),
                ('pms_property_id', '=', self.pms_property_id.id),
                '|',
                '|',
                ('partner_type', '!=', 'customer'),
                ('payment_type', '!=', 'outbound'),
                ('is_internal_transfer', '=', True),
            ]).mapped("remote_id")
            returns_already_migrated_ids = self.env["account.payment"].search([
                ("remote_id", "!=", False),
                ("pms_property_id", "=", self.pms_property_id.id),
                ("payment_type", "=", "outbound"),
                ("partner_type", "=", "customer"),
                ("is_internal_transfer", "=", False),
            ]).mapped("remote_id")

            remote_payment_return_ids = noderpc.env["payment.return"].search([
                ("state", "=", "done"),
                ("line_ids.move_line_ids.payment_id", "in", migrated_payments_remote_ids),
                ("id", "not in", returns_already_migrated_ids),
            ])
            # Mapping Users
            res_users_map_ids = {}
            remote_ids = noderpc.env["res.users"].search([])
            remote_records = noderpc.env["res.users"].browse(remote_ids)
            for record in remote_records:
                res_users = self.env["res.users"].search(
                    [
                        ("login", "=", record.login),
                    ]
                )
                res_users_id = (
                    res_users.id if res_users else self._context.get("uid", self._uid)
                )
                res_users_map_ids.update({str(record.id): res_users_id})
            _logger.info("Migrating 'payment.return'...")
            _logger.info("Total 'payment.return' to migrate: %s" % len(remote_payment_return_ids))
            # disable mail feature to speed-up migration
            context_no_mail = {
                "tracking_disable": True,
                "mail_notrack": True,
                "mail_create_nolog": True,
            }
            for payment_return_id in remote_payment_return_ids:
                remote_payment_return = noderpc.env["payment.return"].browse(
                    payment_return_id
                )
                remote_payment_return_line = remote_payment_return.line_ids

                # prepare related user create_uid
                remote_id = remote_payment_return["create_uid"] and remote_payment_return["create_uid"][0]
                res_create_uid = remote_id and res_users_map_ids.get(str(remote_id))
                journal_id = (
                    self.env["migrated.journal"]
                    .search(
                        [
                            ("migrated_hotel_id", "=", self.id),
                            ("remote_id", "=", remote_payment_return.journal_id.id),
                        ]
                    )
                    .account_journal_id.id
                )
                payment = self.env["account.payment"].search([
                    ("remote_id", "=", remote_payment_return_line.move_line_ids.payment_id.id),
                    ("pms_property_id", "=", self.pms_property_id.id),
                    '|',
                    '|',
                    ('partner_type', '!=', 'customer'),
                    ('payment_type', '!=', 'outbound'),
                    ('is_internal_transfer', '=', True),
                ])
                if payment and payment.folio_ids:
                    folio_id = (
                        self.env["pms.folio"]
                        .search(
                            [
                                ("remote_id", "=", payment.folio_ids[0].id),
                                ("pms_property_id", "=", self.pms_property_id.id),
                            ],
                            limit=1,
                        )
                        .id
                        or False
                    )
                else:
                    folio_id = False
                partner_id = (
                    self.env["migrated.partner"]
                    .search(
                        [
                            ("migrated_hotel_id", "=", self.id),
                            ("remote_id", "=", remote_payment_return_line.partner_id.id),
                        ]
                    )
                    .partner_id.id
                )
                vals = {
                    "journal_id": journal_id,
                    "partner_id": partner_id,
                    "amount": remote_payment_return_line.amount,
                    "date": fields.Datetime.from_string(remote_payment_return.date),
                    "ref": remote_payment_return_line.reference,
                    "payment_type": "outbound",
                    "partner_type": "customer",
                    "state": "draft",
                    "create_uid": res_create_uid,
                    "remote_id": payment_return_id,
                }
                if folio_id:
                    vals["folio_ids"] = [(6, 0, [folio_id])]

                self.with_delay().migrate_payment_return(
                    vals, context_no_mail
                )
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        else:
            noderpc.logout()

    def migrate_payment_return(self, vals, context_no_mail):
        payment_return = (
            self.env["account.payment"]
            .with_context(context_no_mail)
            .create(vals)
        )
        payment_return.with_context(context_no_mail).action_post()

    # INVOICES ---------------------------------------------------------------------------------------------------------------------------

    def _prepare_invoice_remote_data(self, account_invoice, res_users_map_ids, noderpc):
        # search res_users ids
        remote_id = account_invoice["user_id"] and account_invoice["user_id"][0]
        res_user_id = (
            remote_id
            and res_users_map_ids.get(str(remote_id))
            or self._context.get("uid", self._uid)
        )

        # prepare partner_id related field
        default_res_partner = self.env["res.partner"].search(
            [("user_ids", "in", self._context.get("uid", self._uid))]
        )
        # Journal
        journal_id = (
            self.env["migrated.journal"]
            .search(
                [
                    ("remote_id", "=", account_invoice["journal_id"][0]),
                    ("migrated_hotel_id", "=", self.id),
                ]
            )
            .account_journal_id.id
        )
        if not journal_id:
            raise ValidationError(
                "Debes asignar los diarios de facturación en el configurador antes de importar facturas"
            )
        # search res_partner id
        remote_id = account_invoice["partner_id"] and account_invoice["partner_id"][0]
        _logger.info("partner remote_id: %s", remote_id)
        res_partner = (
            self.env["migrated.partner"]
            .search(
                [
                    ("remote_id", "=", remote_id),
                    ("migrated_hotel_id", "=", self.id),
                ]
            )
            .partner_id
            or False
        )
        _logger.info(
            "partner res_partner: %s", res_partner.name if res_partner else "Not Found"
        )
        if not res_partner:
            remote_partner = noderpc.env["res.partner"].browse(remote_id)
            country_id = remote_partner.country_id.id if remote_partner.country_id else False
            if country_id and remote_partner.vat:
                res_partner = self._get_partner_vat(country_id=country_id, vat=remote_partner.vat)
            _logger.info(
                "search vat res_partner: %s",
                res_partner.name if res_partner else "Not Found",
            )
            if not res_partner:
                try:
                    res_partner = (
                        self.env["res.partner"]
                        .with_context(no_vat_validation=True)
                        .create(
                            {
                                "name": remote_partner.name,
                                "vat": remote_partner.vat,
                                "is_company": remote_partner.is_company,
                                "street": remote_partner.street,
                                "street2": remote_partner.street2,
                                "city": remote_partner.city,
                                "zip": remote_partner.zip,
                                "phone": remote_partner.phone,
                                "mobile": remote_partner.mobile,
                                "email": remote_partner.email,
                                "remote_id": remote_partner.id,
                                "country_id": country_id,
                            }
                        )
                    )
                    self.env["migrated.partner"].create(
                        {
                            "partner_id": res_partner.id,
                            "remote_id": remote_partner.id,
                            "migrated_hotel_id": self.id,
                        }
                    )
                    _logger.info(
                        "create res_partner: %s",
                        res_partner.name if res_partner else "No Created",
                    )
                except (ValueError, ValidationError, Exception) as err:
                    self.env["migrated.log"].create(
                        {
                            "name": err,
                            "date_time": fields.Datetime.now(),
                            "migrated_hotel_id": self.id,
                            "model": "invoice",
                        }
                    )
                    _logger.error(
                        "Remote partner with ID remote: [%s] not found", remote_id
                    )
                    return False
            else:
                self.env["migrated.partner"].create(
                    {
                        "partner_id": res_partner.id,
                        "remote_id": remote_partner.id,
                        "migrated_hotel_id": self.id,
                    }
                )
        # take into account merged partners are not active
        # if not res_partner_id:
        #     res_partner_id = self.env['res.partner'].search([
        #         ('remote_id', '=', remote_id),
        #         ('active', '=', False)
        #     ]).main_partner_id.id or None
        # res_partner_id = res_partner_id or default_res_partner.id

        # search related refund_invoice_id
        refund_invoice_id = None
        if account_invoice["refund_invoice_id"]:
            refund_invoice_id = (
                self.env["account.move"]
                .search(
                    [
                        ("remote_id", "=", account_invoice["refund_invoice_id"][0]),
                        ("pms_property_id", "=", self.pms_property_id.id),
                    ]
                )
                .id
                or None
            )

        remote_ids = (
            account_invoice["invoice_line_ids"] and account_invoice["invoice_line_ids"]
        )
        invoice_lines = noderpc.env["account.invoice.line"].search_read(
            [("id", "in", remote_ids)]
        )
        invoice_line_cmds = []
        # prepare invoice lines
        for invoice_line in invoice_lines:
            res_folio_sale_lines = self.env["folio.sale.line"]
            # search for reservation in sale_order_line
            remote_reservation_ids = (
                noderpc.env["hotel.reservation"].search(
                    [("id", "in", invoice_line["reservation_ids"])]
                )
                or None
            )
            if remote_reservation_ids:
                reservation_lines = (
                    self.env["pms.reservation"]
                    .search(
                        [
                            ("pms_property_id", "=", self.pms_property_id.id),
                            ("remote_id", "in", remote_reservation_ids),
                        ]
                    )
                    .reservation_line_ids
                    or None
                )
                if not reservation_lines:
                    # Try to force folio import
                    remote_reservations = noderpc.env["hotel.reservation"].search_read(
                        [("id", "in", remote_reservation_ids)], ["folio_id"]
                    )
                    remote_folio_ids = list(
                        {res["folio_id"][0] for res in remote_reservations}
                    )
                    self.action_migrate_folios(remote_folio_ids)
                    reservation_lines = (
                        self.env["pms.reservation"]
                        .search(
                            [
                                ("pms_property_id", "=", self.pms_property_id.id),
                                ("remote_id", "in", remote_reservation_ids),
                            ]
                        )
                        .reservation_line_ids
                        or None
                    )
                    if not reservation_lines:
                        _logger.warning(
                            "Invoice migration cancel, not reservation in V14: %s",
                            invoice_line["name"],
                        )
                        return False
                res_folio_sale_lines += reservation_lines.sale_line_ids

            # search for services in sale_order_line
            remote_service_ids = (
                noderpc.env["hotel.service"].search(
                    [("id", "in", invoice_line["service_ids"])]
                )
                or None
            )
            if remote_service_ids:
                service_lines = (
                    self.env["pms.service"]
                    .search(
                        [
                            ("pms_property_id", "=", self.pms_property_id.id),
                            ("remote_id", "in", remote_service_ids),
                        ]
                    )
                    .service_line_ids
                    or None
                )
                res_folio_sale_lines = (
                    service_lines.sale_line_ids if service_lines else False
                )

            if not remote_reservation_ids and not remote_service_ids:
                remote_folio_ids = self.env["pms.folio"].search(
                    [
                        ("pms_property_id", "=", self.pms_property_id.id),
                        ("remote_id", "=", account_invoice["folio_ids"]),
                    ]
                )
            res_folio_sale_lines_cmds = (
                res_folio_sale_lines and [[6, False, res_folio_sale_lines.ids]] or False
            )
            product_id = False
            if res_folio_sale_lines and len(res_folio_sale_lines) == 1:
                product_id = res_folio_sale_lines.product_id.id or False
            # take invoice line taxes
            invoice_line_tax_ids = False
            remote_tax = noderpc.env["account.tax"].browse(
                invoice_line["invoice_line_tax_ids"]
            )
            if remote_tax:
                invoice_line_tax_ids = (
                    self.env["account.tax"]
                    .search(
                        [
                            ("company_id", "=", self.company_id.id),
                            ("name", "=", remote_tax.name),
                        ]
                    )
                    .ids
                    or False
                )
            vals = {
                "display_name": invoice_line["name"],
                "name": invoice_line["name"],
                "product_id": product_id,
                # 'origin': invoice_line['origin'],
                "folio_line_ids": res_folio_sale_lines and res_folio_sale_lines_cmds,
                # [480, '700000 Ventas de mercaderías en España']
                # 'account_id': invoice_line['account_id'] and invoice_line['account_id'][0] or 480,
                "price_unit": invoice_line["price_unit"],
                "quantity": invoice_line["quantity"],
                "discount": invoice_line["discount"],
                # 'product_uom_id': invoice_line['uom_id'] and invoice_line['uom_id'][0] or 1,
            }
            if invoice_line_tax_ids:
                vals["tax_ids"] = [[6, False, invoice_line_tax_ids]]
            invoice_line_cmds.append((0, False, vals))

        vals = {
            "remote_id": account_invoice["id"],
            "name": account_invoice["number"],
            "ref": account_invoice["origin"],
            "invoice_date": account_invoice["date_invoice"],
            "move_type": account_invoice["type"],
            "journal_id": journal_id,
            # 'refund_invoice_id': account_invoice['refund_invoice_id'] and refund_invoice_id,
            # [193, '430000 Clientes (euros)']
            # 'account_id': account_invoice['account_id'] and account_invoice['account_id'][0] or 193,
            "partner_id": res_partner.id,
            # [1, 'EUR']
            # 'currency_id': account_invoice['currency_id'] and account_invoice['currency_id'][0] or 1,
            # 'comment': account_invoice['comment'],
            "invoice_line_ids": invoice_line_cmds,
            "invoice_user_id": res_user_id,
            "pms_property_id": self.pms_property_id.id,
        }
        if account_invoice["date_invoice"] < "2023-01-01":
            vals["fiscal_position_id"] = self.env["account.fiscal.position"].search([
                ("company_id", "=", self.company_id.id),
                ("sii_active", "=", False),
            ])

        return vals

    def action_migrate_invoices(self, remote_invoice_ids=False, final=False):
        self.ensure_one()
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        try:
            # prepare res.users ids
            _logger.info("Mapping local with remote 'res.users' ids...")
            remote_ids = noderpc.env["res.users"].search([])
            remote_records = noderpc.env["res.users"].browse(remote_ids)
            res_users_map_ids = {}
            for record in remote_records:
                res_users_id = (
                    self.env["res.users"]
                    .search(
                        [
                            ("login", "=", record.login),
                        ]
                    )
                    .id
                    or self._context.get("uid", self._uid)
                )
                res_users_map_ids.update({str(record.id): res_users_id})

            _logger.info("Preparing 'account.invoice' of interest...")
            import_datetime = fields.Datetime.now()
            migrated_account_invoices = (
                self.env["account.move"].search(
                    [
                        ("remote_id", "!=", False),
                        ("pms_property_id", "=", self.pms_property_id.id),
                        ("move_type", "in", ["out_invoice", "out_refund"]),
                    ]
                )
                or []
            )
            if migrated_account_invoices:
                migrated_account_invoice_ids = migrated_account_invoices.mapped("remote_id")
            else:
                migrated_account_invoice_ids = []
            if not remote_invoice_ids:
                if not final:
                    remote_account_invoice_ids = noderpc.env["account.invoice"].search(
                        [
                            ("number", "not in", [False]),
                            (
                                "date_invoice",
                                ">=",
                                self.migration_date_from.strftime(
                                    DEFAULT_SERVER_DATE_FORMAT
                                ),
                            ),
                            (
                                "date_invoice",
                                "<=",
                                self.migration_date_to.strftime(DEFAULT_SERVER_DATE_FORMAT),
                            ),
                            ("id", "not in", migrated_account_invoice_ids),
                        ],
                        order="id ASC",  # ensure refunded invoices are retrieved after the normal invoice
                    )
                else:
                    remote_account_invoice_ids = noderpc.env["account.invoice"].search(
                        [
                            ("number", "not in", [False]),
                            (
                                "date_invoice",
                                ">=",
                                self.migration_date_to.strftime(
                                    DEFAULT_SERVER_DATE_FORMAT
                                ),
                            ),
                            ("id", "not in", migrated_account_invoice_ids),
                        ],
                        order="id ASC",  # ensure refunded invoices are retrieved after the normal invoice
                    )
            else:
                remote_account_invoice_ids = noderpc.env["account.invoice"].search(
                    [
                        ("id", "in", remote_invoice_ids),
                        ("id", "not in", migrated_account_invoice_ids),
                    ],
                    order="id ASC",  # ensure refunded invoices are retrieved after the normal invoice
                )
            _logger.info("Migrating 'account.invoice'...")
            _logger.info(
                "Total of 'account.invoice' to migrate: %s"
                % len(remote_account_invoice_ids)
            )
            # disable mail feature to speed-up migration
            total = len(remote_account_invoice_ids)
            i = 0
            min_data_invoice_company = self.pms_property_id.company_id.check_min_partner_data_invoice
            invoice_journals = self.env["account.journal"].search(
                [
                    ("type", "=", "sale"),
                    ("company_id", "=", self.pms_property_id.company_id.id),
                    ("pms_property_ids", "in", self.pms_property_id.id),
                ]
            )
            invoice_journals.check_chronology = False
            self.pms_property_id.company_id.check_min_partner_data_invoice = False
            for remote_account_invoice_id in remote_account_invoice_ids:
                try:
                    i += 1
                    _logger.info(str(i) + " of " + str(total) + " migration")
                    _logger.info(
                        "User #%s started migration of account.invoice with remote ID: [%s]",
                        self._uid,
                        remote_account_invoice_id,
                    )
                    rpc_account_invoice = noderpc.env[
                        "account.invoice"
                    ].search_read(
                        [("id", "=", remote_account_invoice_id)],
                        [
                            "user_id",
                            "partner_id",
                            "refund_invoice_id",
                            "invoice_line_ids",
                            "id",
                            "number",
                            "origin",
                            "date_invoice",
                            "type",
                            "payment_ids",
                            "journal_id",
                            "folio_ids",
                        ],
                    )[
                        0
                    ]
                    if rpc_account_invoice["number"].strip() == "":
                        continue
                    vals = self._prepare_invoice_remote_data(
                        rpc_account_invoice,
                        res_users_map_ids,
                        noderpc,
                    )
                    if not vals:
                        continue
                    self.with_delay().create_migration_invoice(
                        vals, rpc_account_invoice["payment_ids"]
                    )
                except (ValueError, ValidationError, Exception) as err:
                    migrated_log = self.env["migrated.log"].create(
                        {
                            "name": err,
                            "date_time": fields.Datetime.now(),
                            "migrated_hotel_id": self.id,
                            "model": "invoice",
                            "remote_id": remote_account_invoice_id,
                        }
                    )
                    _logger.error(
                        "Remote account.invoice with ID remote: [%s] with ERROR LOG #%s: (%s)",
                        remote_account_invoice_id,
                        migrated_log.id,
                        err,
                    )
                    continue
            self.pms_property_id.company_id.check_min_partner_data_invoice = min_data_invoice_company
            self.last_import_invoices = import_datetime
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        else:
            noderpc.logout()

    def create_migration_invoice(self, vals, remote_payment_ids):
        context_no_mail = {
            "tracking_disable": True,
            "mail_notrack": True,
            "mail_create_nolog": True,
        }

        migrated_account_invoice = (
            self.env["account.move"].with_context(context_no_mail).create(vals)
        )
        migrated_account_invoice.message_post_with_view(
            "mail.message_origin_link",
            values={
                "self": migrated_account_invoice,
                "origin": migrated_account_invoice.folio_ids,
            },
            subtype_id=self.env.ref("mail.mt_note").id,
        )
        # this function require a valid vat number in the associated partner_id
        migrated_account_invoice.action_post()
        #
        payment_ids = (
            self.env["account.payment"]
            .search([("remote_id", "in", remote_payment_ids)])
            .ids
            or None
        )
        #
        if payment_ids and migrated_account_invoice.payment_state == "not_paid":
            migrated_account_invoice._autoreconcile_folio_payments()

    def _update_special_field_names(
        self, local_model, remote_model, res_users_map_ids, noderpc
    ):
        # prepare record ids
        _logger.info("Updating '%s' special field names..", local_model)
        records = self.env[local_model].search(
            [("remote_id", ">", 0), ("pms_property_id", "=", self.pms_property_id.id)]
        )
        rpc_records = noderpc.env[remote_model].search_read(
            [("id", "in", records.mapped("remote_id"))],
            ["id", "create_uid", "create_date"],
        )
        for record in records:
            try:
                rpc_record = [
                    res for res in rpc_records if res["id"] == record.remote_id
                ]
                if rpc_record:
                    rpc_record = rpc_record[0]
                    create_uid = (
                        rpc_record["create_uid"]
                        and rpc_record["create_uid"][0]
                        or False
                    )
                    create_uid = (
                        create_uid and res_users_map_ids.get(str(create_uid)) or self._uid
                    )
                    create_date = (
                        rpc_record["create_date"]
                        and rpc_record["create_date"]
                        or record.create_date
                    )

                    self.env.cr.execute(
                        """UPDATE """
                        + self.env[local_model]._table
                        + """
                                           SET create_uid = %s, create_date = %s WHERE id = %s""",
                        (create_uid, create_date, record.id),
                    )

                    _logger.info(
                        "User #%s has updated %s with ID [local, remote]: [%s, %s] - ",
                        self._uid,
                        local_model,
                        record.id,
                        record.remote_id,
                    )
                else:
                    _logger.error(
                        "record dont found (%s), local [%s]: remote (%s)",
                        local_model,
                        record.id,
                        record.remote_id,
                    )

            except (ValueError, ValidationError, Exception) as err:
                _logger.error(
                    "Failed updating hotel.folio with ID [local]: [%s] with ERROR LOG #%s: (%s)",
                    record.id,
                    err,
                )
                continue

    def action_update_special_field_names(self):
        self.ensure_one()
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        try:
            # prepare res.users ids
            _logger.info("Mapping local with remote 'res.users' ids...")
            _logger.info("Mapping local with remote 'res.users' ids...")
            remote_ids = noderpc.env["res.users"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            remote_records = noderpc.env["res.users"].browse(remote_ids)
            res_users_map_ids = {}
            for record in remote_records:
                if record.login in ["default", "portaltemplate", "public"]:
                    continue
                res_user = (
                    self.env["res.users"]
                    .sudo()
                    .search(
                        [
                            ("login", "=", record.login),
                            "|",
                            ("active", "=", True),
                            ("active", "=", False),
                        ]
                    )
                )
                if record.id == 1:
                    res_user = self.backend_id.parent_id.user_id
                    if not res_user:
                        raise ValidationError(
                            _("Debes establecer el usuario en el backend de Wubook")
                        )

                if not res_user:
                    new_partner = (
                        self.env["res.partner"]
                        .sudo()
                        .create(
                            {
                                "name": record.name,
                                "email": record.email,
                            }
                        )
                    )
                    context = {
                        "tracking_disable": True,
                        "mail_notrack": True,
                        "mail_create_nolog": True,
                        "id_no_validate": True,
                    }
                    res_user = (
                        self.env["res.users"]
                        .sudo()
                        .with_context(context)
                        .create(
                            {
                                "partner_id": new_partner.id,
                                "email": record.email,
                                "login": record.login,
                                "company_ids": [
                                    (4, self.pms_property_id.company_id.id)
                                ],
                                "company_id": self.pms_property_id.company_id.id,
                                "pms_property_ids": [(4, self.pms_property_id.id)],
                                "pms_property_id": self.pms_property_id.id,
                            }
                        )
                    )
                    res_user.active = False
                if self.pms_property_id.company_id.id not in res_user.company_ids.ids:
                    res_user.sudo().write(
                        {
                            "company_ids": [(4, self.pms_property_id.company_id.id)],
                        }
                    )
                if self.pms_property_id.id not in res_user.pms_property_ids.ids:
                    res_user.sudo().write(
                        {
                            "pms_property_ids": [(4, self.pms_property_id.id)],
                        }
                    )
                res_users_id = (
                    res_user.id if res_user else self._context.get("uid", self._uid)
                )
                res_users_map_ids.update({str(record.id): res_users_id})

            self._update_special_field_names(
                "pms.folio", "hotel.folio", res_users_map_ids, noderpc
            )
            self._update_special_field_names(
                "pms.reservation", "hotel.reservation", res_users_map_ids, noderpc
            )
            self._update_special_field_names(
                "account.payment", "account.payment", res_users_map_ids, noderpc
            )
            self._update_special_field_names(
                "account.move", "account.invoice", res_users_map_ids, noderpc
            )

        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        else:
            noderpc.logout()

    # CLEAN (review)-----

    def action_clean_up(self):
        self.ensure_one()
        # disable Odoo 10 products
        product_product = self.env["product.product"].search([("remote_id", ">", 0)])
        product_product.product_tmpl_id.write({"active": False})
        product_product.write({"active": False})
        # disable specific closure_reason created for migration ¿?

    # DEBUG --------------

    def action_migrate_debug(self):
        self.ensure_one()
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)

        import wdb

        wdb.set_trace()

    @api.model
    def cron_migrate_partners(self):
        hotel = self.env[self._name].search([])
        hotel.action_migrate_partners()

    @api.model
    def cron_migrate_folios(self):
        hotel = self.env[self._name].search([])
        hotel.action_migrate_folios()

    @api.model
    def cron_migrate_reservations(self):
        hotel = self.env[self._name].search([])
        hotel.action_migrate_reservations()

    @api.model
    def cron_migrate_services(self):
        hotel = self.env[self._name].search([])
        hotel.action_migrate_services()

    @api.model
    def cron_migrate_invoices(self):
        hotel = self.env[self._name].search([])
        hotel.action_migrate_invoices()

    @api.model
    def cron_migrate_account_models(self):
        hotel = self.env[self._name].search([])
        hotel.action_migrate_payments()
        hotel.action_migrate_payment_returns()
        hotel.action_migrate_invoices()

    @api.model
    def cron_migrate_hotel(self):
        self.cron_migrate_partners()
        self.cron_migrate_folios()
        self.cron_migrate_reservations()
        self.cron_migrate_services()

    @api.model
    def cron_update_special_field_names(self):
        hotel = self.env[self._name].search([])
        hotel.action_update_special_field_names()

    def create_backend(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            if not self.backend_id:
                remote_backend_id = noderpc.env["channel.backend"].search([])
                remote_backend = noderpc.env["channel.backend"].browse(
                    remote_backend_id
                )
                if remote_backend:
                    property_code = remote_backend.lcode
                    backend_14 = self.env["channel.wubook.backend"].search(
                        [
                            ("property_code", "=", property_code),
                        ]
                    )
                    if backend_14:
                        raise UserError(
                            "Backend already exists: %s", backend_14.username
                        )
                    user_wubook = self.env["res.users"].search(
                        [
                            ("login", "ilike", "wubook"),
                            ("company_id", "=", self.pms_property_id.company_id.id),
                        ]
                    )
                    user_wubook.pms_property_ids = [(4, self.pms_property_id.id)]
                    remote_parity_pricelist_id = noderpc.env[
                        "channel.product.pricelist"
                    ].search(
                        [("odoo_id", "=", remote_backend.wubook_parity_pricelist_id.id)]
                    )
                    remote_parity_pricelist = noderpc.env[
                        "channel.product.pricelist"
                    ].browse(remote_parity_pricelist_id)
                    general_backend = self.env["channel.backend"].create(
                        {
                            "name": self.pms_property_id.name
                            + " ("
                            + remote_backend.username
                            + ")",
                            "pms_property_id": self.pms_property_id.id,
                            "user_id": user_wubook.id,
                            "backend_type_id": self.env["channel.backend.type"]
                            .search([])[0]
                            .id,
                            "export_disabled": True,
                        }
                    )
                    self.backend_id = self.env["channel.wubook.backend"].create(
                        {
                            "parent_id": general_backend.id,
                            "username": remote_backend.username,
                            "password": remote_backend.passwd,
                            "property_code": remote_backend.lcode,
                            "wubook_journal_id": self.wubook_journal_id.id,
                            "pkey": remote_backend.pkey,
                            "pricelist_external_id": remote_parity_pricelist.external_id,
                        }
                    )
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("backend import error:%s", err)

    def import_pricelists(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Importing Remote Pricelists...")
            import_datetime = fields.Datetime.now()
            remote_ids = noderpc.env["product.pricelist"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            remote_records = noderpc.env["product.pricelist"].browse(remote_ids)
            pricelist_migrated_ids = self.mapped("migrated_pricelist_ids.remote_id")
            for record in remote_records:
                name = record.name if record.active else record.name + " (Obsoleta)"
                match_record = self.env["product.pricelist"].search(
                    [
                        ("name", "=", record.name),
                    ]
                )
                # TODO: Create Binding Wubook??
                if record.id not in pricelist_migrated_ids:
                    self.migrated_pricelist_ids = [
                        (
                            0,
                            0,
                            {
                                "remote_id": record.id,
                                "remote_name": name,
                                "last_sync": fields.Datetime.now(),
                                "migrated_hotel_id": self.id,
                                "pms_pricelist_id": match_record.id
                                if match_record
                                else False,
                            },
                        )
                    ]
                    if match_record.pms_property_ids:
                        match_record.pms_property_ids = [(4, self.pms_property_id.id)]
                    _logger.info("Pricelist imported: %s", record.name)
            self.last_import_pricelists = import_datetime
            self.count_migrated_pricelists = len(self.migrated_pricelist_ids)
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("pricelist import error:%s", err)

    def import_room_type_classes(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Importing Remote Room Types Classes...")
            remote_ids = noderpc.env["hotel.room.type.class"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            remote_records = noderpc.env["hotel.room.type.class"].browse(remote_ids)
            room_type_class_migrated_ids = self.mapped(
                "migrated_room_type_class_ids.remote_id"
            )
            for record in remote_records:
                match_record = self.env["pms.room.type.class"].search(
                    [
                        "|",
                        ("name", "=", record.name),
                        ("default_code", "=", record.code_class),
                    ]
                )
                # TODO: Create Binding Wubook??
                if record.id not in room_type_class_migrated_ids:
                    name = record.name if record.active else record.name + " (Obsoleta)"
                    self.migrated_room_type_class_ids = [
                        (
                            0,
                            0,
                            {
                                "remote_id": record.id,
                                "remote_name": name,
                                "last_sync": fields.Datetime.now(),
                                "migrated_hotel_id": self.id,
                                "pms_room_type_class_id": match_record.id
                                if match_record and len(match_record) == 1
                                else False,
                            },
                        )
                    ]
                    if match_record.pms_property_ids:
                        match_record.pms_property_ids = [(4, self.pms_property_id.id)]
                    _logger.info("RoomType Class imported: %s", record.name)
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("roomtype class import error:%s", err)

    def import_room_types(self):
        if not self.migrated_room_type_class_ids:
            raise UserError(
                _("You must configure room type class previusly to room types import")
            )
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Importing Remote Room Types...")
            remote_ids = noderpc.env["hotel.room.type"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            remote_records = noderpc.env["hotel.room.type"].browse(remote_ids)
            room_type_migrated_ids = self.mapped("migrated_room_type_ids.remote_id")
            for record in remote_records:
                match_record = self.env["pms.room.type"].search(
                    [
                        "|",
                        ("name", "=", record.name),
                        ("default_code", "=", record.code_class),
                    ]
                )
                # TODO: Create Binding Wubook??
                if record.id not in room_type_migrated_ids:
                    name = record.name if record.active else record.name + " (Obsoleta)"
                    self.migrated_room_type_ids = [
                        (
                            0,
                            0,
                            {
                                "remote_id": record.id,
                                "remote_name": name,
                                "last_sync": fields.Datetime.now(),
                                "migrated_hotel_id": self.id,
                                "pms_room_type_id": match_record.id
                                if match_record and len(match_record) == 1
                                else False,
                            },
                        )
                    ]
                    if match_record.pms_property_ids:
                        match_record.pms_property_ids = [(4, self.pms_property_id.id)]
                    _logger.info("RoomType imported: %s", record.name)
            self.count_migrated_room_types = len(self.migrated_room_type_ids)
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("roomtype import error:%s", err)

    def import_rooms(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Importing Remote Rooms...")
            for room_type in self.env["migrated.room.type"].search([("migrated_hotel_id", "=", self.id)]).mapped("pms_room_type_id"):
                if room_type.pms_property_ids and self.pms_property_id not in room_type.pms_property_ids:
                    room_type.pms_property_ids = [(4, self.pms_property_id.id)]
            import_datetime = fields.Datetime.now()
            remote_ids = noderpc.env["hotel.room"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            remote_records = noderpc.env["hotel.room"].browse(remote_ids)
            room_migrated_ids = self.mapped("migrated_room_ids.remote_id")
            total_records = len(remote_records)
            count = 0
            for record in remote_records:
                if record.shared_room_id:
                    room_clean_name = record.name
                    # if record.shared_room_id.equivalent_room_id.id not in room_migrated_ids:
                    #     new_room = self.env["pms.room"].create(
                    #         {
                    #             "name": record.shared_room_id.equivalent_room_id.name,
                    #             "pms_property_id": self.pms_property_id.id,
                    #             "capacity": record.shared_room_id.equivalent_room_id.capacity,
                    #             "room_type_id": self.env["migrated.room.type"].search(
                    #                 [
                    #                     ("migrated_hotel_id", "=", self.id),
                    #                     ("remote_id", "=", record.shared_room_id.equivalent_room_id.room_type_id.id),
                    #                 ]
                    #             ).pms_room_type_id.id,
                    #             "extra_beds_allowed": record.shared_room_id.equivalent_room_id.extra_beds_allowed,
                    #             "sequence": record.shared_room_id.equivalent_room_id.sequence,
                    #             "active": record.shared_room_id.equivalent_room_id.active,
                    #             "in_ine": record.shared_room_id.equivalent_room_id.in_ine,
                    #         }
                    #     )
                    #     self.migrated_room_ids = [
                    #         (
                    #             0,
                    #             0,
                    #             {
                    #                 "remote_id": record.shared_room_id.equivalent_room_id.id,
                    #                 "remote_name": record.shared_room_id.equivalent_room_id.name,
                    #                 "last_sync": import_datetime,
                    #                 "migrated_hotel_id": self.id,
                    #                 "pms_room_id": new_room.id,
                    #             },
                    #         )
                    #     ]
                else:
                    room_clean_name = [
                        int(item) for item in record.name.split() if item.isdigit()
                    ]
                    room_clean_name = (
                        str(room_clean_name[0]) if len(room_clean_name) == 1 else False
                    )
                match_record = self.env["pms.room"].search(
                    [
                        ("pms_property_id", "=", self.pms_property_id.id),
                        "|",
                        ("name", "=", record.name),
                        ("name", "=", room_clean_name),
                    ]
                )
                if record.id not in room_migrated_ids:
                    room_name = (
                        record.name if record.active else record.name + " (Obsoleta)"
                    )
                    if match_record:
                        self.migrated_room_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": room_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                    "pms_room_id": match_record.id
                                    if match_record and len(match_record) == 1
                                    else False,
                                },
                            )
                        ]
                        count += 1
                        _logger.info(
                            "(%s/%s) Room Matching imported: %s",
                            total_records,
                            count,
                            record.name,
                        )
                    elif self.auto_create_rooms:
                        room_type = self.migrated_room_type_ids.filtered(
                            lambda r: r.remote_id == record.room_type_id.id
                        ).pms_room_type_id
                        if not room_type:
                            raise UserError(
                                _(
                                    "Room type dont found in v14 mapping: %s",
                                    record.room_type_id.name,
                                )
                            )
                        # parent_id = False
                        # if record.shared_room_id and record.shared_room_id.equivalent_room_id:
                        #     parent_id = self.migrated_room_ids.filtered(
                        #         lambda r: r.remote_id == record.shared_room_id.equivalent_room_id.id
                        #     ).pms_room_id.id
                        new_room = self.env["pms.room"].create(
                            {
                                "name": room_clean_name or record.name,
                                "room_type_id": room_type.id,
                                "capacity": record.capacity,
                                "extra_beds_allowed": record.extra_beds_allowed,
                                "sequence": record.sequence,
                                "in_ine": record.in_ine,
                                "pms_property_id": self.pms_property_id.id,
                                "active": record.active,
                                # "parent_id": parent_id,
                            }
                        )
                        count += 1
                        self.migrated_room_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": room_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                    "pms_room_id": new_room.id,
                                },
                            )
                        ]
                        _logger.info(
                            "(%s/%s) Remote Room created: %s",
                            total_records,
                            count,
                            record.name,
                        )
                    else:
                        self.migrated_room_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": room_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                },
                            )
                        ]
                        count += 1
                        _logger.info(
                            "(%s/%s) Room imported without v14 related: %s",
                            total_records,
                            count,
                            record.name,
                        )
            self.last_import_rooms = import_datetime
            self.count_migrated_rooms = len(self.migrated_room_ids)
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("room import error:%s", err)

    def import_products(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Importing Remote Products...")
            import_datetime = fields.Datetime.now()
            remote_ids = noderpc.env["product.product"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            # We want discard room type products associated
            remote_room_type_ids = noderpc.env["hotel.room.type"].search([])
            remote_room_types = noderpc.env["hotel.room.type"].browse(
                remote_room_type_ids
            )
            remote_product_discard_ids = []
            for room_type in remote_room_types:
                remote_product_discard_ids.append(room_type.product_id.id)

            remote_records = noderpc.env["product.product"].browse(remote_ids)
            product_migrated_ids = self.mapped("migrated_product_ids.remote_id")
            total_records = len(remote_records)
            count = 0
            for record in remote_records:
                if record.id in remote_product_discard_ids:
                    continue
                match_record = self.env["product.product"].search(
                    [
                        ("name", "=", record.name),
                    ]
                )
                if record.id not in product_migrated_ids:
                    product_name = (
                        record.name if record.active else record.name + " (Obsoleto)"
                    )
                    if match_record:
                        self.migrated_product_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": product_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                    "product_id": match_record.id
                                    if match_record and len(match_record) == 1
                                    else False,
                                },
                            )
                        ]
                        if match_record.pms_property_ids:
                            match_record.pms_property_ids = [
                                (4, self.pms_property_id.id)
                            ]
                        count += 1
                        _logger.info(
                            "(%s/%s) Product Matching imported: %s",
                            total_records,
                            count,
                            record.name,
                        )
                    elif not record.active:
                        self.migrated_product_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": product_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                    "product_id": self.dummy_product_id.id,
                                },
                            )
                        ]
                        count += 1
                        _logger.info(
                            "(%s/%s) Product Matching imported: %s",
                            total_records,
                            count,
                            record.name,
                        )
                    elif self.auto_create_products:
                        new_product = self.env["product.product"].create(
                            {
                                "name": record.name,
                                "pms_property_ids": [(4, self.pms_property_id.id)],
                                "list_price": record.list_price,
                                "type": "service",
                                "is_extra_bed": record.is_extra_bed,
                                "per_day": record.per_day,
                                "per_person": record.per_person,
                                "daily_limit": record.daily_limit,
                                "consumed_on": record.consumed_on,
                                "active": record.active,
                            }
                        )
                        count += 1
                        self.migrated_product_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": product_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                    "product_id": new_product.id,
                                },
                            )
                        ]
                        _logger.info(
                            "(%s/%s) Remote Product created: %s",
                            total_records,
                            count,
                            record.name,
                        )
                    else:
                        self.migrated_product_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": product_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                },
                            )
                        ]
                        count += 1
                        _logger.info(
                            "(%s/%s) Product imported without v14 related: %s",
                            total_records,
                            count,
                            record.name,
                        )
            self.last_import_products = import_datetime
            self.count_migrated_products = len(self.migrated_product_ids)
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("product import error:%s", err)

    def import_board_services(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Importing Remote Board Services...")
            remote_ids = noderpc.env["hotel.board.service"].search([])
            remote_records = noderpc.env["hotel.board.service"].browse(remote_ids)
            board_service_migrated_ids = self.mapped(
                "migrated_board_service_ids.remote_id"
            )
            for record in remote_records:
                board_service_name = record.name
                match_record = self.env["pms.board.service"].search(
                    [
                        ("name", "=", record.name),
                    ]
                )
                # TODO: Create Binding Wubook??
                if record.id not in board_service_migrated_ids:
                    self.migrated_board_service_ids = [
                        (
                            0,
                            0,
                            {
                                "remote_id": record.id,
                                "remote_name": board_service_name,
                                "last_sync": fields.Datetime.now(),
                                "migrated_hotel_id": self.id,
                                "board_service_id": match_record.id
                                if match_record and len(match_record) == 1
                                else False,
                            },
                        )
                    ]
                    if match_record.pms_property_ids:
                        match_record.pms_property_ids = [(4, self.pms_property_id.id)]
                    _logger.info("Board Service Class imported: %s", record.name)
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("boardservice class import error:%s", err)

    def import_board_service_room_types(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            for product in self.env["migrated.product"].search([("migrated_hotel_id", "=", self.id)]).mapped("product_id"):
                if product.pms_property_ids and self.pms_property_id not in product.pms_property_ids:
                    product.pms_property_ids = [(4, self.pms_property_id.id)]
            for board in self.env["migrated.board.service"].search([("migrated_hotel_id", "=", self.id)]).mapped("board_service_id"):
                if board.pms_property_ids and self.pms_property_id not in board.pms_property_ids:
                    board.pms_property_ids = [(4, self.pms_property_id.id)]
            for product in self.env["migrated.product"].search([("migrated_hotel_id", "=", self.id)]).mapped("product_id"):
                if product.pms_property_ids and self.pms_property_id not in product.pms_property_ids:
                    product.pms_property_ids = [(4, self.pms_property_id.id)]
            _logger.info("Importing Remote Board Services Room types...")
            import_datetime = fields.Datetime.now()
            remote_ids = noderpc.env["hotel.board.service.room.type"].search([])
            remote_records = noderpc.env["hotel.board.service.room.type"].browse(
                remote_ids
            )
            board_service_room_type_migrated_ids = self.mapped(
                "migrated_board_service_room_type_ids.remote_id"
            )
            total_records = len(remote_records)
            count = 0
            for record in remote_records:
                room_type_id = self.migrated_room_type_ids.filtered(
                    lambda b: b.remote_id == record.hotel_room_type_id.id
                ).pms_room_type_id.id
                if not room_type_id:
                    raise UserError(
                        _(
                            "Room type dont found in v14 mapping: %s",
                            record.hotel_room_type_id.name,
                        )
                    )
                board_service_id = self.migrated_board_service_ids.filtered(
                    lambda b: b.remote_id == record.hotel_board_service_id.id
                ).board_service_id.id
                if not board_service_id:
                    raise UserError(
                        _(
                            "Main Board Service dont found in v14 mapping: %s",
                            record.hotel_board_service_id.name,
                        )
                    )
                match_record = self.env["pms.board.service.room.type"].search(
                    [
                        ("pms_board_service_id", "=", board_service_id),
                        ("pms_room_type_id", "=", room_type_id),
                        ("pms_property_id", "=", self.pms_property_id.id),
                    ]
                )
                if record.id not in board_service_room_type_migrated_ids:
                    board_service_room_type_name = (
                        match_record.display_name if match_record else record.name
                    )
                    if match_record:
                        self.migrated_board_service_room_type_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": board_service_room_type_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                    "board_service_room_type_id": match_record.id
                                    if match_record and len(match_record) == 1
                                    else False,
                                },
                            )
                        ]
                        count += 1
                        _logger.info(
                            "(%s/%s) Board Service Room Type Matching imported: %s",
                            total_records,
                            count,
                            record.name,
                        )
                    elif self.auto_create_board_service_room_types:
                        # Prepare board service room type lines
                        line_vals = []
                        remote_line_ids = record.board_service_line_ids
                        for line in remote_line_ids:
                            product_id = self.migrated_product_ids.filtered(
                                lambda b: b.remote_id == line.product_id.id
                            ).product_id.id
                            if not product_id:
                                remote_product_id = noderpc.env[
                                    "product.product"
                                ].search(
                                    [
                                        ("id", "=", line.product_id.id),
                                        "|",
                                        ("active", "=", True),
                                        ("active", "=", False),
                                    ]
                                )
                                remote_product = noderpc.env["product.product"].browse(
                                    remote_product_id
                                )
                                if remote_product:
                                    new_product = self.env["product.product"].create(
                                        {
                                            "name": remote_product.name,
                                            "pms_property_ids": [
                                                (4, self.pms_property_id.id)
                                            ],
                                            "list_price": remote_product.list_price,
                                            "type": "service",
                                            "is_extra_bed": remote_product.is_extra_bed,
                                            "per_day": remote_product.per_day,
                                            "per_person": remote_product.per_person,
                                            "daily_limit": remote_product.daily_limit,
                                            "consumed_on": remote_product.consumed_on,
                                            "active": False,
                                        }
                                    )
                                    product_id = new_product.id
                                else:
                                    raise UserError(
                                        _(
                                            "Product dont found in v14 mapping: %s",
                                            line.product_id.name,
                                        )
                                    )
                            line_vals.append(
                                (
                                    0,
                                    0,
                                    {
                                        "product_id": product_id,
                                        "amount": line.amount,
                                    },
                                )
                            )
                        new_board = self.env["pms.board.service.room.type"].create(
                            {
                                "pms_room_type_id": room_type_id,
                                "board_service_line_ids": line_vals,
                                "pms_board_service_id": board_service_id,
                                "pms_property_id": self.pms_property_id.id,
                            }
                        )
                        count += 1
                        self.migrated_board_service_room_type_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": board_service_room_type_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                    "board_service_room_type_id": new_board.id,
                                },
                            )
                        ]
                        _logger.info(
                            "(%s/%s) Board Service Room Type created: %s",
                            total_records,
                            count,
                            record.name,
                        )
                    else:
                        self.migrated_board_service_room_type_ids = [
                            (
                                0,
                                0,
                                {
                                    "remote_id": record.id,
                                    "remote_name": board_service_room_type_name,
                                    "last_sync": fields.Datetime.now(),
                                    "migrated_hotel_id": self.id,
                                },
                            )
                        ]
                        count += 1
                        _logger.info(
                            "(%s/%s) Board Service Room Type imported without v14 related: %s",
                            total_records,
                            count,
                            record.display_name,
                        )
            self.last_import_board_services = import_datetime
            self.count_migrated_board_services = len(
                self.migrated_board_service_room_type_ids
            )
        except (ValueError, ValidationError, Exception) as err:
            _logger.error("Board services import error: %s", err)

    def import_journals(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Importing Remote Jorunals...")
            remote_ids = noderpc.env["account.journal"].search(
                [
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )
            remote_records = noderpc.env["account.journal"].browse(remote_ids)
            journal_migrated_ids = self.mapped("migrated_journal_ids.remote_id")
            for record in remote_records:
                match_record = self.env["account.journal"].search(
                    [
                        ("name", "=", record.name),
                        ("company_id", "=", self.pms_property_id.company_id.id),
                        "|",
                        ("pms_property_ids", "=", False),
                        ("pms_property_ids", "in", self.pms_property_id.id),
                    ]
                )
                if record.id not in journal_migrated_ids:
                    journal_name = (
                        record.name if record.active else record.name + " (Obsoleto)"
                    )
                    self.migrated_journal_ids = [
                        (
                            0,
                            0,
                            {
                                "remote_id": record.id,
                                "remote_name": journal_name,
                                "last_sync": fields.Datetime.now(),
                                "migrated_hotel_id": self.id,
                                "account_journal_id": match_record.id
                                if match_record
                                else False,
                            },
                        )
                    ]
                    if match_record.pms_property_ids:
                        match_record.pms_property_ids = [(4, self.pms_property_id.id)]
                    _logger.info("Journal imported: %s", record.name)
            self.count_migrated_journals = len(self.migrated_journal_ids)
        except (ValueError, ValidationError, Exception) as err:
            self.env["migrated.log"].create(
                {
                    "name": err,
                    "date_time": fields.Datetime.now(),
                    "migrated_hotel_id": self.id,
                    "model": "journal",
                    "remote_id": record.id,
                }
            )
            _logger.error("journal import error:%s", err)

    def import_channel_types(self):
        _logger.info("Creating remote channel types...")
        remote_channels = [
            ("door", "Puerta"),
            ("mail", "Mail"),
            ("phone", "Telefono"),
            ("call", "Call Center"),
            ("web", "Website"),
            ("agency", "Agencia"),
            ("operator", "Touroperador"),
            ("virtualdoor", "Virtual Door"),
            ("detour", "Desvío"),
        ]
        for channel in remote_channels:
            match_record = self.env["pms.sale.channel"].search(
                [
                    ("name", "=", channel[1]),
                ]
            )
            if channel[0] not in self.migrated_channel_type_ids.mapped("remote_name"):
                self.migrated_channel_type_ids = [
                    (
                        0,
                        0,
                        {
                            "remote_name": channel[0],
                            "last_sync": fields.Datetime.now(),
                            "migrated_hotel_id": self.id,
                            "channel_type_id": match_record.id
                            if match_record and len(match_record) == 1
                            else False,
                        },
                    )
                ]
                _logger.info("RoomType Class imported: %s", channel[1])

    def chunks(self, l, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(l), n):
            yield l[i : i + n]

    def _get_folio_note(self, remote_hotel_folio):
        note = "<p>Migrated from: <b>" + self.odoo_host + "</b>: </p>"
        for key, val in remote_hotel_folio.items():
            note += "<p><b>" + key + ": </b>" + str(val) + "</p>"
        return note

    def _get_reservation_note(
        self, remote_reservation, remote_res_lines, remote_service
    ):
        note = "<p>Migrated from: <b>" + self.odoo_host + ":<b></p>"
        for key, val in remote_reservation[0].items():
            if key == "reservation_line_ids" and val:
                note += "<p><b>Reservation Lines:</b></p>"
                for line in remote_res_lines:
                    note += "<p><b>-> " + line["date"] + "</b></p>"
                    for key, val in line.items():
                        if key == "date":
                            continue
                        note += "<b>" + key + ": </b>" + str(val) + ", "
            if key == "service_ids" and val:
                note += "<p><b>Services:</b></p>"
                for service in remote_service:
                    note += "<p><b>-> " + service["name"] + "</b></p>"
                    for key, val in service.items():
                        if key == "name":
                            continue
                        note += "<b>" + key + ": </b>" + str(val) + ","
            else:
                note += "<p><b>" + key + ": </b>" + str(val) + "</p>"
        return note

    def ensure_matching_payment_invoices(self, journal_id):
        invoices = self.env["account.move"].search(
            [
                ("journal_id", "=", journal_id),
                ("amount_residual", ">", 0),
            ]
        )
        for move in invoices:
            to_reconcile_payments_widget_vals = json.loads(
                move.invoice_outstanding_credits_debits_widget
            )
            if not to_reconcile_payments_widget_vals:
                continue
            current_amounts = {
                vals["move_id"]: vals["amount"]
                for vals in to_reconcile_payments_widget_vals["content"]
            }
            pay_term_lines = move.line_ids.filtered(
                lambda line: line.account_id.user_type_id.type
                in ("receivable", "payable")
            )
            to_propose = (
                self.env["account.move"]
                .browse(list(current_amounts.keys()))
                .line_ids.filtered(
                    lambda line: line.account_id == pay_term_lines.account_id
                    and not line.reconciled
                    and (
                        line.folio_ids in move.folio_ids
                        or (
                            line.move_id.partner_id == move.partner_id
                            or not line.move_id.partner_id
                        )
                    )
                )
            )
            to_reconcile = move.match_pays_by_amount(payments=to_propose, invoice=move)
            if to_reconcile:
                (pay_term_lines + to_reconcile).reconcile()
                # Set partner in payment
                for record in to_reconcile:
                    if record.payment_id and not record.payment_id.partner_id:
                        record.payment_id.partner_id = move.partner_id
                    if (
                        record.statement_line_id
                        and not record.statement_line_id.partner_id
                    ):
                        record.statement_line_id.partner_id = move.partner_id

    def _account_close_migration_past_years(self):
        # limit date is included in search
        limit_date = datetime.datetime(2021, 1, 31)
        journals = self.env["account.journal"].search(
            [
                ("company_id", "=", self.company_id.id),
            ]
        )
        for journal in journals:
            lines = self.env["account.move.line"].search(
                [
                    ("journal_id", "=", journal.id),
                    ("date", "<=", limit_date),
                    ("pms_property_id", "=", self.pms_property_id.id),
                ]
            )
            if not lines:
                continue
            for past_year in range(min(lines.mapped("date")).year, limit_date.year):
                year_lines = lines.filtered(lambda l: l.date.year == past_year)
                sum(year_lines.balance)

    # Go to live in production by the next stepts:
    # 1.- Create binging between wubook and odoo in roomtypes, pricelist and wubook restrictions
    # 2.- Import availability rules and prices from V2 to Odoo
    # 3.- Import last Folios from the last imported data to future, set confirm all draft v2 folios
    # 4.- Import last Payments from the last imported data to future
    # 5.- Import last Returns from the last imported data to future
    # 6.- Import last Invoices from the last imported data to future
    # 7.- Update special fields names (create_uid and create_date)
    # 8.- Desactivate V2 Wubook and activate V3 Wubook

    def _get_completed_migration_partners(self):
        job_batch_id = self.env.ref("migrated_hotel.job_migrated_hotel_partner_batch").id
        job_function_id = self.env.ref("migrated_hotel.job_migrated_hotel_partners").id
        active_migrate_partners_jobs = self.env["queue.job"].search(
            [
                ("state", "=", "pending"),
                ("job_function_id", "in", [job_batch_id, job_function_id]),
            ]
        )
        if self.step >= 2 and not active_migrate_partners_jobs:
            return True
        return False

    def _compute_completed_migration_folios(self):
        job_batch_id = self.env.ref("migrated_hotel.job_migrated_hotel_folios_batch").id
        job_function_id = self.env.ref("migrated_hotel.job_migrated_hotel_folios").id
        active_migrate_folios_jobs = self.env["queue.job"].search(
            [
                ("state", "in", ["pending", "enqueued", "started"]),
                ("job_function_id", "in", [job_batch_id, job_function_id]),
            ]
        )
        failed_migrate_folios_jobs = self.env["queue.job"].search(
            [
                ("state", "=", "failed"),
                ("job_function_id", "in", [job_batch_id, job_function_id]),
                ('date_created', '>=' , self.last_created_jobs_datetime)
            ]
        )
        if self.step >= 3 and not active_migrate_folios_jobs and not failed_migrate_folios_jobs:
            self.complete_folios = True
            self.count_total_job_folios = self.count_pending_job_folios = self.count_failed_job_folios = 0
        else:
            total_migrate_folios_jobs = self.env["queue.job"].search(
                [
                    ("job_function_id", "in", [job_batch_id, job_function_id]),
                    ('date_created', '>=' , self.last_created_jobs_datetime)
                ]
            )
            self.complete_folios = False
            self.count_pending_job_folios = len(active_migrate_folios_jobs)
            self.count_failed_job_folios = len(failed_migrate_folios_jobs)
            self.count_total_job_folios = len(total_migrate_folios_jobs)

    def _compute_completed_migration_payments(self):
        job_batch_id = self.env.ref("migrated_hotel.job_migrated_hotel_payments").id
        job_function_id = self.env.ref("migrated_hotel.job_migrated_bank_payments").id
        active_migrate_payments_jobs = self.env["queue.job"].search(
            [
                ("state", "in", ["pending", "enqueued", "started"]),
                ("job_function_id", "in", [job_batch_id, job_function_id]),
            ]
        )
        failed_migrate_payments_jobs = self.env["queue.job"].search(
            [
                ("state", "=", "failed"),
                ("job_function_id", "in", [job_batch_id, job_function_id]),
                ('date_created', '>=' , self.last_created_jobs_datetime)
            ]
        )
        if self.step >= 4 and not active_migrate_payments_jobs and not failed_migrate_payments_jobs:
            self.complete_payments = True
            self.count_total_job_payments = self.count_pending_job_payments = self.count_failed_job_payments = 0
        else:
            total_migrate_payments_jobs = self.env["queue.job"].search(
                [
                    ("job_function_id", "in", [job_batch_id, job_function_id]),
                    ('date_created', '>=' , self.last_created_jobs_datetime)
                ]
            )
            self.complete_payments = False
            self.count_pending_job_payments = len(active_migrate_payments_jobs)
            self.count_failed_job_payments = len(failed_migrate_payments_jobs)
            self.count_total_job_payments = len(total_migrate_payments_jobs)

    def _compute_completed_returns(self):
        job_batch_id = self.env.ref("migrated_hotel.job_migrated_payment_return").id
        active_migrate_returns_jobs = self.env["queue.job"].search(
            [
                ("state", "in", ["pending", "enqueued", "started"]),
                ("job_function_id", "=", job_batch_id),
            ]
        )
        failed_migrate_returns_jobs = self.env["queue.job"].search(
            [
                ("state", "=", "failed"),
                ("job_function_id", "=", job_batch_id),
                ('date_created', '>=' , self.last_created_jobs_datetime)
            ]
        )
        if self.step >= 5 and not active_migrate_returns_jobs and not failed_migrate_returns_jobs:
            self.complete_returns = True
            self.count_total_job_returns = self.count_pending_job_returns = self.count_failed_job_returns = 0
        else:
            total_migrate_returns_jobs = self.env["queue.job"].search(
                [
                    ("job_function_id", "=", job_batch_id),
                    ('date_created', '>=' , self.last_created_jobs_datetime)
                ]
            )
            self.complete_returns = False
            self.count_pending_job_returns = len(active_migrate_returns_jobs)
            self.count_failed_job_returns = len(failed_migrate_returns_jobs)
            self.count_total_job_returns = len(total_migrate_returns_jobs)

    def _compute_completed_migration_invoices(self):
        job_batch_id = self.env.ref("migrated_hotel.job_migrated_hotel_invoices").id
        active_migrate_invoices_jobs = self.env["queue.job"].search(
            [
                ("state", "in", ["pending", "enqueued", "started"]),
                ("job_function_id", "=", job_batch_id),
            ]
        )
        failed_migrate_invoices_jobs = self.env["queue.job"].search(
            [
                ("state", "=", "failed"),
                ("job_function_id", "=", job_batch_id),
                ('date_created', '>=' , self.last_created_jobs_datetime)
            ]
        )
        if self.step >= 6 and not active_migrate_invoices_jobs and not failed_migrate_invoices_jobs:
            self.complete_invoices = True
            self.count_total_job_invoices = self.count_pending_job_invoices = self.count_failed_job_invoices = 0
        else:
            total_migrate_invoices_jobs = self.env["queue.job"].search(
                [
                    ("job_function_id", "=", job_batch_id),
                    ('date_created', '>=' , self.last_created_jobs_datetime)
                ]
            )
            self.complete_invoices = False
            self.count_pending_job_invoices = len(active_migrate_invoices_jobs)
            self.count_failed_job_invoices = len(failed_migrate_invoices_jobs)
            self.count_total_job_invoices = len(total_migrate_invoices_jobs)

    def _compute_next_step(self):
        if (
            self.complete_boards and self.complete_journals and self.complete_pricelists
            and self.complete_products and self.complete_rooms
        ):
            self.next_step = str(self.step + 1)
        else:
            self.next_step = '0'

    def _inverse_next_step(self):
        step = int(self.next_step) - 1
        if step < 0:
            step = 0
        self.step = step

    def step1_create_bindings(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            _logger.info("Creating binding ids in room_types")
            room_types = self.env["pms.room.type"].search([
                ("pms_property_ids", "in", self.pms_property_id.id),
            ])
            for room_type in room_types:
                if not room_type.channel_wubook_bind_ids.filtered(lambda b: b.backend_id == self.backend_id):
                    remote_id = self.env["migrated.room.type"].search([
                        ("pms_room_type_id", "=", room_type.id),
                        ("migrated_hotel_id", "=", self.id),
                    ]).remote_id
                    remote = noderpc.env["channel.hotel.room.type"].search_read(
                        [("odoo_id", "=", remote_id)], ["external_id"]
                    )
                    if remote:
                        room_type.channel_wubook_bind_ids = [(0, 0, {
                            "backend_id": self.backend_id.id,
                            "external_id": int(remote[0]["external_id"]),
                        })]
            _logger.info("Creating binding ids in pricelist")
            pricelists = self.env["product.pricelist"].search([
                '|',
                ("pms_property_ids", "=", False),
                ("pms_property_ids", "in", self.pms_property_id.id),
            ])
            for pricelist in pricelists:
                if not pricelist.channel_wubook_bind_ids.filtered(lambda b: b.backend_id == self.backend_id):
                    remote = self.env["migrated.pricelist"].search([
                        ("pms_pricelist_id", "=", pricelist.id),
                        ("migrated_hotel_id", "=", self.id),
                    ])
                    if remote:
                        remote_id = remote[0].remote_id
                        remote = noderpc.env["channel.product.pricelist"].search_read(
                            [("odoo_id", "=", remote_id)], ["external_id"]
                        )
                        if remote:
                            pricelist.channel_wubook_bind_ids = [(0, 0, {
                                "backend_id": self.backend_id.id,
                                "external_id": int(remote[0]["external_id"]),
                            })]
                        if pricelist == self.wubook_parity_pricelist_id:
                            self.backend_id.pricelist_external_id = int(remote[0]["external_id"])
                    else:
                        _logger.warning("Pricelist %s not found in V11" % pricelist.name)
                else:
                    _logger.info("Pricelist %s already connected with Wubook" % pricelist.name)

            self.env.cr.commit()

            _logger.info("Creating binding ids in availability_plans")
            availability_plan = self.wubook_restriccion_plan_id
            if availability_plan and not availability_plan.channel_wubook_bind_ids.filtered(lambda b: b.backend_id == self.backend_id):
                availability_plan.channel_wubook_bind_ids = [(0, 0, {
                    "backend_id": self.backend_id.id,
                    "external_id": -1,
                })]
            self.step = 1

            _logger.info("Creating binding in property")
            self.pms_property_id.channel_wubook_bind_ids = [(0, 0, {
                "backend_id": self.backend_id.id,
                "external_id": uuid.uuid4().hex,
            })]

        except Exception as err:
            raise ValidationError(err)

    def step2_import_rule_and_prices(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            if self.migration_date_to - fields.Date.today() > datetime.timedelta(days=10):
                raise ValidationError(
                    _("Migration date to must be less than 10 days from today by security reasons")
                )
            _logger.info("Importing rules and prices")
            pricelists = self.env["product.pricelist"].search([
                ("pricelist_type", "=", "daily"),
                '|',
                ("pms_property_ids", "=", False),
                ("pms_property_ids", "in", self.pms_property_id.id),
            ])

            remote_pricelists = noderpc.env["product.pricelist"].browse(
                self.env["migrated.pricelist"].search([
                    ("pms_pricelist_id", "in", pricelists.ids),
                    ("migrated_hotel_id", "=", self.id),
                ]).mapped("remote_id")
            )

            items = noderpc.env["product.pricelist.item"].search_read(
                [
                    ("pricelist_id", "in", remote_pricelists.ids),
                    ("date_start", ">=", fields.Date.today().strftime("%Y-%m-%d")),
                ],
                ["date_start", "date_end", "fixed_price", "product_tmpl_id", "pricelist_id"],
            )

            for item in items:
                pricelist = self.env["migrated.pricelist"].search([
                    ("remote_id", "=", item["pricelist_id"][0]),
                    ("migrated_hotel_id", "=", self.id),
                ]).pms_pricelist_id
                remote_product_id = noderpc.env["product.product"].search_read(
                    [("product_tmpl_id", "=", item["product_tmpl_id"][0])],
                    ["id", ""],
                )[0]["id"]
                remote_room_type_id = noderpc.env["hotel.room.type"].search_read(
                    [("product_id", "=", remote_product_id)],
                    ["id"],
                )[0]["id"]
                product_id = self.env["migrated.room.type"].search([
                    ("migrated_hotel_id", "=", self.id),
                    ("remote_id", "=", remote_room_type_id),
                ])[0].pms_room_type_id.product_id.id
                vals = {
                    "pricelist_id": pricelist.id,
                    "date_start_consumption": item["date_start"],
                    "date_end_consumption": item["date_end"],
                    "fixed_price": item["fixed_price"],
                    "product_id": product_id,
                    "pms_property_ids": [(6, 0, [self.pms_property_id.id])],
                    "compute_price": "fixed",
                    "applied_on": "0_product_variant",
                }
                item = self.env["product.pricelist.item"].search([
                    ("pricelist_id", "=", pricelist.id),
                    ("date_start_consumption", "=", item["date_start"]),
                    ("product_id", "=", vals["product_id"]),
                    ("pms_property_ids", "=", self.pms_property_id.id),
                ])
                if item:
                    item.write(vals)
                else:
                    self.env["product.pricelist.item"].create(vals)

            _logger.info("Importing rules and prices finished")
            avail_plan = self.env["pms.availability.plan"].browse(self.wubook_restriccion_plan_id.id)

            items = noderpc.env["hotel.room.type.restriction.item"].search_read(
                [
                    ("date", ">=", fields.Date.today().strftime("%Y-%m-%d")),
                ],
                ["date", "room_type_id", "min_stay", "max_stay", "closed"],
            )
            avail_items = noderpc.env["hotel.room.type.availability"].search_read(
                [
                    ("date", ">=", fields.Date.today().strftime("%Y-%m-%d")),
                ],
                ["date", "room_type_id", "quota", "max_avail"],
            )
            max_item_date = max([item["date"] for item in items])
            max_avail_date = max([item["date"] for item in avail_items])
            max_date = max(max_item_date, max_avail_date)

            for date in (datetime.date.today() + datetime.timedelta(days=d) for d in range((fields.Date.from_string(max_date) - datetime.date.today()).days)):
                date_vals = []
                room_type_items = list(filter(lambda item: item["date"] == date.strftime("%Y-%m-%d"), items))
                if room_type_items:
                    for item in room_type_items:
                        date_vals.append({
                            "date": date,
                            "room_type_id": self.env["migrated.room.type"].search(
                                [("remote_id", "=", item["room_type_id"][0]),("migrated_hotel_id", "=", self.id)]
                            ).pms_room_type_id.id,
                            "min_stay": item["min_stay"],
                            "max_stay": item["max_stay"],
                            "closed": item["closed"],
                        })
                room_type_avail_items = list(filter(lambda item: item["date"] == date.strftime("%Y-%m-%d"), avail_items))
                if room_type_avail_items:
                    for item in room_type_avail_items:
                        for date_val in date_vals:
                            if date_val["room_type_id"] == item["room_type_id"][0]:
                                date_val.update({
                                    "quota": item["quota"],
                                    "max_avail": item["max_avail"],
                                })
                                break
                        else:
                            date_vals.append({
                                "date": date,
                                "room_type_id": self.env["migrated.room.type"].search(
                                    [("remote_id", "=", item["room_type_id"][0]),("migrated_hotel_id", "=", self.id)]
                                ).pms_room_type_id.id,
                                "quota": item["quota"],
                                "max_avail": item["max_avail"],
                            })
                if date_vals:
                    for rule_vals in date_vals:
                        rule = self.env["pms.availability.plan.rule"].search(
                            [
                                ("availability_plan_id", "=", avail_plan.id),
                                ("date", "=", date),
                                ("room_type_id", "=", rule_vals["room_type_id"]),
                                ("pms_property_id", "=", self.pms_property_id.id),
                            ]
                        )
                        if rule:
                            rule.write(rule_vals)
                        else:
                            rule_vals.update({
                                "availability_plan_id": avail_plan.id,
                                "pms_property_id": self.pms_property_id.id,
                            })
                            self.env["pms.availability.plan.rule"].create(rule_vals)
            self.step = 2
        except Exception as err:
            raise ValidationError(err)

    def step3_import_last_folio(self):
        _logger.info("Importing folios")
        if self.migration_date_to - fields.Date.today() > datetime.timedelta(days=10):
            raise ValidationError(
                _("Migration date to must be less than 10 days from today by security reasons")
            )
        self.last_created_jobs_datetime = fields.Datetime.now()
        self.action_migrate_folios(final=True)
        self.step = 3

    def step4_import_last_payments(self):
        _logger.info("Importing payments")
        if self.migration_date_to - fields.Date.today() > datetime.timedelta(days=10):
            raise ValidationError(
                _("Migration date to must be less than 10 days from today by security reasons")
            )
        self.last_created_jobs_datetime = fields.Datetime.now()
        self.action_migrate_payments(final=True)
        self.step = 4

    def step5_import_last_returns(self):
        _logger.info("Importing returns")
        if self.migration_date_to - fields.Date.today() > datetime.timedelta(days=10):
            raise ValidationError(
                _("Migration date to must be less than 10 days from today by security reasons")
            )
        self.last_created_jobs_datetime = fields.Datetime.now()
        self.action_migrate_payment_returns()
        self.step = 5

    def step6_import_last_invoices(self):
        _logger.info("Importing invoices")
        if self.migration_date_to - fields.Date.today() > datetime.timedelta(days=10):
            raise ValidationError(
                _("Migration date to must be less than 10 days from today by security reasons")
            )
        self.last_created_jobs_datetime = fields.Datetime.now()
        self.action_migrate_invoices(final=True)
        self.step = 6

    def step7_update_special_field_names(self):
        _logger.info("Updating special field names")
        self.action_update_special_field_names()
        self.step = 7

    def step8_go_to_live(self):
        try:
            noderpc = odoorpc.ODOO(self.odoo_host, self.odoo_protocol, self.odoo_port)
            noderpc.login(self.odoo_db, self.odoo_user, self.odoo_password)
        except (
            odoorpc.error.RPCError,
            odoorpc.error.InternalError,
            urllib.error.URLError,
        ) as err:
            raise ValidationError(err)
        try:
            # Disabled Wubook channel and Crons in V11
            _logger.info("Disabling Wubook channel and Crons in V11")
            Backend = noderpc.env["channel.backend"]
            remote_backend_id = noderpc.env["channel.backend"].search([])
            remote_backend = Backend.browse(remote_backend_id)
            remote_backend.username = "DISABLED"
            remote_backend.server = "DISABLED"
            Crons = noderpc.env["ir.cron"]
            remote_cron_ids = noderpc.env["ir.cron"].search([])
            remote_crons = Crons.browse(remote_cron_ids)
            for remote_cron in remote_crons:
                remote_cron.active = False

            _logger.info("Configuring Wubook channel in V14")
            # 5- Create wubook token, active push and export_disabled = False in channel local
            self.backend_id.parent_id.export_disabled = False
            self.backend_id.generate_security_key()
            self.backend_id.set_push_url()

            # 6 - Active check_chronology in journals
            invoice_journals = self.env["account.journal"].search(
                [
                    ("type", "=", "sale"),
                    ("company_id", "=", self.pms_property_id.company_id.id),
                    ("pms_property_ids", "in", self.pms_property_id.id),
                ]
            )
            invoice_journals.check_chronology = True

            # 7- confirmar folios en borrador

            folios = self.env["pms.folio"].search([
                ("pms_property_id", "=", self.pms_property_id.id),
                ("state", "=", "draft"),
                ("reservation_ids.state", "not in", ["draft", "cancel"]),
            ])
            folios.state = "confirm"
            self.env.cr.commit()

            # 8- Force import booking payments
            _logger.info("Force import booking payments")
            prepaid_folios = self.env["pms.folio"].search([
                ("internal_comment", "ilike", "PRE-PAID"),
                ("agency_id.name", "ilike", "booking"),
                ("payment_state", "=", "not_paid"),
                ("pms_property_id", "=", self.pms_property_id.id),
            ])


            # We need import max 60 by hour to avoid wubook rate limit
            count = 0
            for folio in prepaid_folios:
                folio_reservation_code = folio.channel_wubook_bind_ids.external_id
                eta_time = datetime.datetime.now() + datetime.timedelta(hours=int(count / 50))
                self.env["channel.wubook.pms.folio"].with_delay(
                    eta=eta_time, priority=5
                ).import_record(folio.channel_wubook_bind_ids[0].backend_id, folio_reservation_code)
            self.step = 8

        except Exception as err:
            raise ValidationError(err)

    def _get_partner_vat(self, country_id, vat):
        _eu_country_vat = {
            'GR': 'EL'
        }
        Partner = self.env["res.partner"].with_context(active_test=False).sudo()
        europe = self.env.ref("base.europe")
        if not europe:
            europe = self.env["res.country.group"].search(
                [("name", "=", "Europe")], limit=1
            )
        country = self.env["res.country"].browse(country_id)
        partner_country_code = country.code
        vat_country, vat_number = Partner._split_vat(vat)
        if europe and country.id in europe.country_ids.ids:
            vat_country = _eu_country_vat.get(vat_country, vat_country).upper()
        vat_with_code = (
            vat
            if partner_country_code.upper() == vat_country.upper()
            else partner_country_code.upper() + vat
        )
        vat_without_code = (
            vat
            if partner_country_code.upper() != vat_country.upper()
            else vat_number
        )
        domain = [
            "|",
            ("vat", "ilike", vat_with_code),
            ("vat", "ilike", vat_without_code),
        ]
        repeat_partner = Partner.search(domain, limit=1)
        return repeat_partner

