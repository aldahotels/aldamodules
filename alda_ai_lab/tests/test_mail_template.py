from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from .common import LabCase

BODY = (
    '<p>Hola <t t-out="object.partner_name">cliente</t>, os esperamos el '
    '<span t-field="object.first_checkin"/> en '
    '<t t-out="object.pms_property_id.name"/>.</p>'
)
BODY_GL = '<p>Ola <t t-out="object.partner_name">cliente</t>, agardamos por vós.</p>'


@tagged("post_install", "-at_install")
class TestMailTemplate(LabCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for code in ("es_ES", "gl_ES"):
            cls.env["res.lang"]._activate_lang(code)
        cls.user.groups_id |= cls.env.ref("mail.group_mail_template_editor")
        checkin = date.today() + timedelta(days=7)
        cls.folio = cls.env["pms.folio"].create(
            {
                "pms_property_id": cls.prop.id,
                "partner_name": "Lab guest",
                "sale_channel_origin_id": cls.direct.id,
            }
        )
        cls.env["pms.reservation"].create(
            {
                "folio_id": cls.folio.id,
                "room_type_id": cls.room_type.id,
                "checkin": checkin,
                "checkout": checkin + timedelta(days=2),
            }
        )
        cls.args = {
            "name": "Lab welcome for groups",
            "model": "pms.folio",
            "subject": "Bienvenidos, {{ object.partner_name }}",
            "body_html": BODY,
            "preview_record_id": cls.folio.id,
        }

    def _templates(self):
        return self.env["mail.template"].search([("name", "=", self.args["name"])])

    def test_preview_renders_and_creates_nothing(self):
        preview = self.run_tool("lab_mail_template_create", **self.args)
        (rendered,) = preview["result"]["previews"]
        self.assertEqual(rendered["subject"], "Bienvenidos, Lab guest")
        self.assertIn("Hola Lab guest", rendered["body_html"])
        self.assertIn("Lab hotel", rendered["body_html"])
        self.assertEqual(
            preview["result"]["placeholders"],
            ["first_checkin", "partner_name", "pms_property_id.name"],
        )
        self.assertFalse(self._templates())

    def test_apply_with_galician(self):
        args = dict(
            self.args,
            subject_gl="Benvidos, {{ object.partner_name }}",
            body_html_gl=BODY_GL,
        )
        _preview, applied = self.preview_and_apply("lab_mail_template_create", **args)
        template = self._templates()
        self.assertEqual(template.id, applied["result"]["template_id"])
        self.assertEqual(template.model, "pms.folio")
        self.assertIn("Hola", template.with_context(lang="es_ES").body_html)
        self.assertIn("Ola", template.with_context(lang="gl_ES").body_html)
        self.assertEqual(
            template.with_context(lang="gl_ES").subject,
            "Benvidos, {{ object.partner_name }}",
        )

    def test_dangerous_placeholders_are_refused(self):
        bad_bodies = [
            "<p><t t-out=\"object.env['res.users'].search([])\"/></p>",
            '<p><t t-out="object.sudo().name"/></p>',
            '<p><t t-out="user.name"/></p>',
            '<p><a t-att-href="object.name">x</a></p>',
            '<p><t t-raw="object.name"/></p>',
            "<script>alert(1)</script>",
            "<p>{{ object.name }}</p>",
            '<p><t t-out="object.reservation_ids.name"/></p>',
            '<p><t t-out="object.access_token"/></p>',
            '<p><a href="javascript:alert(1)">x</a></p>',
            '<p style="background: url(https://example.com/x)">x</p>',
        ]
        for body in bad_bodies:
            with self.subTest(body=body), self.assertRaises(UserError):
                self.run_tool(
                    "lab_mail_template_create", **dict(self.args, body_html=body)
                )
        with self.assertRaisesRegex(UserError, "Placeholder not allowed"):
            self.run_tool(
                "lab_mail_template_create",
                **dict(self.args, subject="{{ object.partner_id.vat }}"),
            )
        self.assertFalse(self._templates())

    def test_editors_only(self):
        # Every internal user is an editor unless the rendering is restricted.
        editor = self.env.ref("mail.group_mail_template_editor")
        self.env.ref("base.group_user").implied_ids -= editor
        editor.users -= self.user
        with self.assertRaisesRegex(AccessError, "Mail Template Editor"):
            self.run_tool("lab_mail_template_create", **self.args)
