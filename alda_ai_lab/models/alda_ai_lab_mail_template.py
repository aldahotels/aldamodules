import ast
import re

from lxml import etree, html as lxml_html

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.rendering_tools import INLINE_TEMPLATE_REGEX

from odoo.addons.pms_ai_tool.tools import guarded_tool, truncate

from .lab import lab_silence

MAX_DEPTH = 3
PROPERTY_FIELDS = (
    "name",
    "street",
    "city",
    "zip",
    "phone",
    "email",
    "website",
    "default_arrival_hour",
    "default_departure_hour",
)
# Fields a template may print, per model. Paths that do not exist in this
# database are left out at run time.
PATHS = {
    "pms.folio": {
        "name",
        "partner_name",
        "first_checkin",
        "last_checkout",
        "number_of_rooms",
        "amount_total",
        "pending_amount",
        "external_reference",
        "partner_id.name",
        "agency_id.name",
        "company_id.name",
        "currency_id.symbol",
        "pricelist_id.name",
        "sale_channel_origin_id.name",
        "user_id.name",
        *(f"pms_property_id.{name}" for name in PROPERTY_FIELDS),
    },
    "pms.reservation": {
        "name",
        "partner_name",
        "checkin",
        "checkout",
        "arrival_hour",
        "departure_hour",
        "nights",
        "adults",
        "children",
        "price_total",
        "folio_id.name",
        "partner_id.name",
        "agency_id.name",
        "room_type_id.name",
        "preferred_room_id.name",
        "board_service_room_id.pms_board_service_id.name",
        "currency_id.symbol",
        "pricelist_id.name",
        *(f"pms_property_id.{name}" for name in PROPERTY_FIELDS),
    },
}
BODY_TYPES = frozenset(
    {"char", "text", "integer", "float", "monetary", "date", "selection"}
)
SUBJECT_TYPES = frozenset({"char", "text", "integer", "selection"})
# Expressions owned by the module, never written by the AI.
LANG_EXPRESSION = {
    "pms.folio": "{{ object.lang or object.partner_id.lang }}",
    "pms.reservation": "{{ object.folio_id.lang or object.partner_id.lang }}",
}
PARTNER_EXPRESSION = {
    "pms.folio": "{{ object.partner_id.id or '' }}",
    "pms.reservation": "{{ object.partner_id.id or '' }}",
}
TAGS = {
    "t",
    "p",
    "br",
    "hr",
    "div",
    "span",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "small",
    "h1",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "a",
    "img",
    "blockquote",
}
ATTRIBUTES = {
    "style",
    "href",
    "src",
    "alt",
    "title",
    "width",
    "height",
    "align",
    "valign",
    "colspan",
    "rowspan",
    "border",
    "cellpadding",
    "cellspacing",
}
OUTPUTS = {"t-out", "t-field"}
NO_FIELD_TAGS = {"t", "table", "thead", "tbody", "tr", "td", "th", "ul", "ol", "li"}
HREF_OK = re.compile(r"(https://|mailto:|tel:)", re.I)
BAD_STYLE = re.compile(
    r"url\s*\(|expression\s*\(|javascript:|@import|behavior\s*:", re.I
)
# {{ }} is printed as it is in a QWeb body; the rest is other template syntax.
NOT_QWEB = re.compile(r"\{\{|\}\}|\$\{|#\{|\{%")


class AldaAiLabTemplateTools(models.AbstractModel):
    _name = "alda.ai.lab.template.tools"
    _inherit = "alda.ai.lab.mixin"
    _description = "AI lab tools: mail templates"

    # Validation: the only barrier between the AI text and QWeb

    @api.model
    def _lab_walk(self, model, names):
        """The last field of a path, or None if a step is not allowed."""
        current, field = self.env[model], None
        for position, name in enumerate(names, 1):
            field = current._fields.get(name)
            if not field or (field.groups and not self.user_has_groups(field.groups)):
                return None
            if position < len(names):
                if field.type != "many2one":
                    return None
                current = self.env[field.comodel_name]
        return field

    @api.model
    def _lab_allowed_paths(self, model, types):
        allowed = []
        for path in PATHS[model]:
            field = self._lab_walk(model, path.split("."))
            if field and field.type in types:
                allowed.append(path)
        return sorted(allowed)

    @api.model
    def _lab_path(self, model, expression, types=BODY_TYPES):
        try:
            node = ast.parse(expression.strip(), mode="eval").body
        except SyntaxError:
            node = None
        names = []
        while isinstance(node, ast.Attribute):
            names.insert(0, node.attr)
            node = node.value
        path = ".".join(names)
        field = (
            isinstance(node, ast.Name)
            and node.id == "object"
            and 0 < len(names) <= MAX_DEPTH
            and path in PATHS[model]
            and self._lab_walk(model, names)
        )
        if not field or field.type not in types:
            raise UserError(
                _("Placeholder not allowed: %(expression)s. Use one of: %(paths)s.")
                % {
                    "expression": truncate(expression, 60),
                    "paths": ", ".join(
                        f"object.{path}"
                        for path in self._lab_allowed_paths(model, types)
                    ),
                }
            )
        return path

    @api.model
    def _lab_check_subject(self, model, text):
        if "\n" in text or "${" in text or "{%" in text:
            raise UserError(
                _("The subject is one line with {{ object.field }} placeholders.")
            )
        rest = INLINE_TEMPLATE_REGEX.sub("", text)
        if "{{" in rest or "}}" in rest:
            raise UserError(_("The subject has unbalanced {{ }}."))
        return {
            self._lab_path(model, expression, SUBJECT_TYPES)
            for expression in INLINE_TEMPLATE_REGEX.findall(text)
        }

    @api.model
    def _lab_check_body(self, model, source):  # noqa: C901 - one rule per branch
        if NOT_QWEB.search(source):
            raise UserError(
                _('In the body write <t t-out="object.field"/>, not {{ }} or ${ }.')
            )
        try:
            root = lxml_html.fragment_fromstring(source, create_parent="div")
        except (etree.ParserError, ValueError) as error:
            raise UserError(_("The body is not valid HTML: %s") % error) from None
        paths = set()
        for element in root.iter(etree.Element):
            if element is root:
                continue
            if element.tag not in TAGS:
                raise UserError(_("The tag <%s> is not allowed.") % element.tag)
            outputs = [name for name in element.attrib if name in OUTPUTS]
            for name, value in element.attrib.items():
                if name in OUTPUTS:
                    continue
                if name not in ATTRIBUTES:
                    raise UserError(
                        _("The attribute %(name)s is not allowed on <%(tag)s>.")
                        % {"name": name, "tag": element.tag}
                    )
                if name == "href" and not HREF_OK.match(value.strip()):
                    raise UserError(
                        _("Links must start with https://, mailto: or tel:.")
                    )
                if name == "src" and not value.strip().lower().startswith("https://"):
                    raise UserError(_("Images must be https:// addresses."))
                if name == "style" and BAD_STYLE.search(value):
                    raise UserError(
                        _("The style attribute cannot load addresses or scripts.")
                    )
            if len(outputs) > 1 or (element.tag == "t" and not outputs):
                raise UserError(
                    _('Use <t> only as <t t-out="object.field">default</t>.')
                )
            if outputs:
                if len(element):
                    raise UserError(_("A placeholder cannot contain other tags."))
                if outputs[0] == "t-field" and element.tag in NO_FIELD_TAGS:
                    raise UserError(
                        _("t-field goes on a <span>, not on <%s>.") % element.tag
                    )
                paths.add(self._lab_path(model, element.attrib[outputs[0]]))
        return paths

    # Preview helpers

    @api.model
    def _lab_preview_record(self, model, record_id=None):
        properties = self.env["pms.ai.tools"]._ai_scope_property_ids()
        domain = [("pms_property_id", "in", properties)]
        if record_id:
            domain.append(("id", "=", record_id))
        record = self.env[model].search(domain, order="id desc", limit=1)
        if not record:
            raise UserError(
                _("There is no %(model)s %(id)s in your hotels.")
                % {"model": model, "id": record_id or ""}
            )
        return record

    @api.model
    def _lab_render(self, model, record, subject, body, lang):
        # Never sudo: mail.template renders without restrictions, so the
        # validation above and the user's own rights are the barrier.
        template = self.env["mail.template"].with_context(lang=lang)
        try:
            rendered_subject = template._render_template(subject, model, record.ids)[
                record.id
            ]
            rendered_body = template._render_template(
                body, model, record.ids, engine="qweb", post_process=True
            )[record.id]
        except UserError as error:
            # mail wraps the error with the whole template and a traceback.
            raise UserError(
                _("The template does not render on %(record)s: %(error)s")
                % {
                    "record": record.display_name,
                    "error": truncate(str(error).split("\n", 1)[0], 200),
                }
            ) from None
        return {
            "lang": lang,
            "subject": rendered_subject,
            "body_html": str(rendered_body),
        }

    # Tool

    @guarded_tool(
        input_schema={
            "name": {
                "type": "string",
                "maxLength": 120,
                "description": "Template name.",
            },
            "model": {
                "type": "string",
                "enum": ["pms.folio", "pms.reservation"],
                "description": "pms.folio (one email per booking or group) or "
                "pms.reservation (one per room).",
            },
            "subject": {
                "type": "string",
                "maxLength": 200,
                "description": "Subject in Spanish, with placeholders such as "
                "{{ object.partner_name }}.",
            },
            "body_html": {
                "type": "string",
                "maxLength": 20000,
                "description": "Body in Spanish, HTML. Placeholders: "
                '<t t-out="object.partner_name">guest</t> (the text inside is '
                'printed when the value is empty) or <span t-field="object.'
                'first_checkin"/> for formatted dates and amounts.',
            },
            "subject_gl": {
                "type": "string",
                "maxLength": 200,
                "description": "Subject in Galician (with body_html_gl).",
            },
            "body_html_gl": {
                "type": "string",
                "maxLength": 20000,
                "description": "Body in Galician (with subject_gl).",
            },
            "preview_record_id": {
                "type": "integer",
                "minimum": 1,
                "description": "Folio or reservation to preview with. Default: the "
                "latest of your hotels.",
            },
        },
        output_schema={
            "record": {"type": "object"},
            "placeholders": {"type": "array", "items": {"type": "string"}},
            "previews": {"type": "array", "items": {"type": "object"}},
        },
        required_inputs=["name", "model", "subject", "body_html"],
        write=True,
        apply="_ai_lab_mail_template_create_apply",
        # The previews carry the data of a guest.
        log_result=False,
    )
    def _ai_lab_mail_template_create(
        self,
        name,
        model,
        subject,
        body_html,
        subject_gl=None,
        body_html_gl=None,
        preview_record_id=None,
    ):
        self._lab_check()
        if not self.env.user.has_group("mail.group_mail_template_editor"):
            raise AccessError(
                _(
                    "Creating templates with placeholders needs the group Mail "
                    "Template Editor."
                )
            )
        self.env["mail.template"].check_access_rights("create")
        if NOT_QWEB.search(name):
            raise UserError(_("The name is plain text."))
        if bool(subject_gl) != bool(body_html_gl):
            raise UserError(_("Give subject_gl and body_html_gl together, or neither."))
        Lang = self.env["res.lang"]
        base_lang = "es_ES" if Lang._lang_get_id("es_ES") else "en_US"
        versions = {base_lang: (subject, body_html)}
        if subject_gl:
            if not Lang._lang_get_id("gl_ES"):
                raise UserError(
                    _("Galician is not active here: its version cannot be stored.")
                )
            versions["gl_ES"] = (subject_gl, body_html_gl)
        placeholders = set()
        for version_subject, version_body in versions.values():
            placeholders |= self._lab_check_subject(model, version_subject)
            placeholders |= self._lab_check_body(model, version_body)
        record = self._lab_preview_record(model, preview_record_id)
        previews = [
            self._lab_render(model, record, version_subject, version_body, lang)
            for lang, (version_subject, version_body) in versions.items()
        ]
        warnings = [
            _(
                "Lab tool: only for staging. The template is not used by any "
                "automatic sending; anyone sending it by hand from staging puts real "
                "data in the staging mail catcher, which anyone can read."
            )
        ]
        if self.env["mail.template"].search_count(
            [("model", "=", model), ("name", "=", name)]
        ):
            warnings.append(
                _("A template called %s already exists for this model.") % name
            )
        return {
            "summary": _(
                "Template %(name)s for %(model)s in %(langs)s, previewed with "
                "%(record)s."
            )
            % {
                "name": name,
                "model": model,
                "langs": ", ".join(versions),
                "record": record.display_name,
            },
            "definitions": [
                _(
                    "Placeholders take the data of each guest when the email is "
                    "sent; the language is the guest's, falling back to Spanish."
                )
            ],
            "warnings": warnings,
            "result": {
                "record": {"id": record.id, "name": record.display_name},
                "placeholders": sorted(placeholders),
                "previews": previews,
            },
            # What the creation depends on, not the rendered guest data.
            "binding": {
                "name": name,
                "model": model,
                "langs": sorted(versions),
                "placeholders": sorted(placeholders),
            },
            "plan": {
                "base_lang": base_lang,
                "vals": {
                    "name": name,
                    "model_id": self.env["ir.model"]._get_id(model),
                    "subject": subject,
                    "body_html": body_html,
                    "lang": LANG_EXPRESSION[model],
                    "partner_to": PARTNER_EXPRESSION[model],
                    "use_default_to": False,
                    "auto_delete": True,
                    "description": _("Created with the AI lab by %s (staging demo).")
                    % self.env.user.name,
                },
                "gl": {"subject": subject_gl, "body_html": body_html_gl}
                if subject_gl
                else None,
            },
        }

    def _ai_lab_mail_template_create_apply(self, plan, **arguments):
        self._lab_check()
        Template = self.env["mail.template"].with_context(lang=plan["base_lang"])
        with lab_silence(Template) as templates:
            template = templates.create(plan["vals"])
            if plan["gl"]:
                for field_name, value in plan["gl"].items():
                    # Raises on an inactive language instead of overwriting
                    # the text other languages fall back to.
                    template.update_field_translations(field_name, {"gl_ES": value})
        return {
            "summary": _(
                "Template %(name)s created. Open it and use Preview to try other "
                "records and languages."
            )
            % {"name": template.name},
            "result": {
                "template_id": template.id,
                "url": self._lab_url(template),
                "languages": [plan["base_lang"]] + (["gl_ES"] if plan["gl"] else []),
            },
        }
