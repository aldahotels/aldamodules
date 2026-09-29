from contextlib import contextmanager
from unittest.mock import patch

from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import Forbidden

from odoo.http import Response
from odoo.tests import tagged

from odoo.addons.website.tools import MockRequest

from ..controllers import main as controllers_main
from ..controllers.main import HelpdeskFormController
from .common import AldaHelpdeskPmsCase


@tagged("post_install", "-at_install")
class TestWebsiteTicketForm(AldaHelpdeskPmsCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = HelpdeskFormController()
        cls.website = cls.env.ref("website.default_website")
        cls.public_user = cls.env.ref("base.public_user")

    @contextmanager
    def _request(self, user):
        # ensure_db() resolves the database from the request host, which a
        # mocked request does not have.
        with MockRequest(
            self.env(user=user), website=self.website
        ) as request, patch.object(controllers_main, "ensure_db"):
            request.is_frontend = False
            request.httprequest.files = MultiDict()
            request.render = lambda template, qcontext=None, **kw: Response(
                template=template, qcontext=qcontext
            )
            yield request

    def _confirmation(self, user, ticket, access_token=None):
        with self._request(user):
            kwargs = {"ticket_id": ticket.id}
            if access_token is not None:
                kwargs["access_token"] = access_token
            return self.controller.helpdesk_ticket_thankyou(**kwargs)

    def test_confirmation_requires_token(self):
        response = self._confirmation(self.public_user, self.ticket_a)
        self.assertFalse(response.qcontext["ticket"])
        self.assertFalse(response.qcontext["ticket_url"])

    def test_confirmation_rejects_wrong_token(self):
        response = self._confirmation(self.public_user, self.ticket_a, "wrong-token")
        self.assertFalse(response.qcontext["ticket"])
        self.assertFalse(response.qcontext["ticket_url"])

    def test_confirmation_with_token(self):
        token = self.ticket_a.sudo()._portal_ensure_token()
        response = self._confirmation(self.public_user, self.ticket_a, token)
        self.assertEqual(response.qcontext["ticket"], self.ticket_a)
        self.assertIn(token, response.qcontext["ticket_url"])

    def _submit(self, user, **post):
        values = {
            "team_id": str(self.team.id),
            "property_id": str(self.property_a.id),
            "subject": "Website ticket",
            "description": "Website ticket description",
            "priority": "0",
        }
        values.update(post)
        with self._request(user):
            return self.controller.helpdesk_ticket_submit(**values)

    def _last_ticket(self):
        return self.env["helpdesk.ticket"].search([], order="id desc", limit=1)

    def test_submit_redirects_with_token_and_uses_user_partner(self):
        other_partner = self.env["res.partner"].create({"name": "Other partner"})
        last_ticket = self._last_ticket()
        response = self._submit(self.helpdesk_user, partner_id=str(other_partner.id))
        ticket = self._last_ticket()
        self.assertNotEqual(ticket, last_ticket)
        self.assertEqual(ticket.partner_id, self.helpdesk_user.partner_id)
        self.assertEqual(ticket.pms_property_id, self.property_a)
        self.assertTrue(ticket.access_token)
        self.assertIn(
            f"/helpdesk/ticket/confirmation/{ticket.id}"
            f"?access_token={ticket.access_token}",
            response.location,
        )

    def test_submit_requires_login(self):
        last_ticket = self._last_ticket()
        response = self._submit(self.public_user, property_id="")
        self.assertIn("/web/login", response.location)
        self.assertEqual(self._last_ticket(), last_ticket)

    def test_submit_rejects_team_not_offered(self):
        hidden_team = self.env["helpdesk.team"].create(
            {
                "name": "Test Hidden Team",
                "privacy_visibility": "internal",
                "member_ids": [(6, 0, self.creator.ids)],
            }
        )
        with self.assertRaises(Forbidden):
            self._submit(self.helpdesk_user, team_id=str(hidden_team.id))

    def test_form_rejects_foreign_property(self):
        for route in (
            self.controller.helpdesk_ticket_form,
            self.controller.helpdesk_ticket_purchase_form,
        ):
            with self._request(self.helpdesk_user), self.assertRaises(Forbidden):
                route(property_id=str(self.property_b.id))

    def test_form_with_own_property(self):
        with self._request(self.helpdesk_user):
            response = self.controller.helpdesk_ticket_form(
                property_id=str(self.property_a.id)
            )
        self.assertEqual(response.template, "alda_helpdesk_pms.create_ticket_form")
        self.assertEqual(response.qcontext["property_id"], self.property_a.id)
