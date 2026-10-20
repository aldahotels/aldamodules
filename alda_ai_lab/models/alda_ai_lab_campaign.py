import hashlib
import re

from lxml import etree, html as lxml_html
from markupsafe import Markup

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import (
    email_normalize,
    html2plaintext,
    html_sanitize,
    is_html_empty,
)

from odoo.addons.pms_ai_tool.models.pms_salesperson_tools import (
    DATE_TO_INPUT,
    SALESPEOPLE_INPUT,
)
from odoo.addons.pms_ai_tool.tools import guarded_tool

from .lab import lab_silence

COOLING_TOOL = "pms_ai_tool.ai_tool_pms_salesperson_cooling_customers"
COOLING_TOP = 50
MAX_RECIPIENTS = 200
LAB_MARK = "[LAB]"
PLACEHOLDERS = re.compile(r"\{\{|\}\}")
SAFE_HREF = re.compile(r"^(https?://|mailto:|tel:)", re.IGNORECASE)
LAYOUT = Markup(
    '<div class="o_layout oe_unremovable oe_unmovable bg-200 o_basic_theme" '
    'data-name="Mailing" style="margin:0;padding:24px 16px 10px;'
    'background-color:#ffffff;"><div class="oe_structure">'
    '<div class="o_mail_no_options" style="max-width:600px;'
    "font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;"
    'color:#000000;">{content}<p style="margin:24px 0 0 0;font-size:12px;">'
    '<a href="/unsubscribe_from_list" style="color:#6c757d;">{unsubscribe}</a>'
    "</p></div></div></div>"
)
BLACKLIST_QUERY = """
SELECT email FROM mail_blacklist WHERE active AND email = ANY(%(emails)s)
"""
OPTED_OUT_QUERY = """
SELECT mc.email_normalized
  FROM mailing_contact mc
  JOIN mailing_contact_list_rel rel ON rel.contact_id = mc.id
 WHERE mc.email_normalized = ANY(%(emails)s)
 GROUP BY mc.email_normalized
HAVING bool_and(rel.opt_out)
"""


class AldaAiLabCampaignTools(models.AbstractModel):
    _name = "alda.ai.lab.campaign.tools"
    _inherit = "alda.ai.lab.mixin"
    _description = "AI lab tools: email campaigns"

    @api.model
    def _lab_plain_text(self, label, text):
        text = " ".join((text or "").split())
        if PLACEHOLDERS.search(text):
            # The subject is an inline template and the preheader becomes
            # QWeb when the mailing is sent.
            raise UserError(_("The %s cannot contain {{ }} placeholders.") % label)
        return text

    @api.model
    def _lab_clean_body(self, body):
        """Sanitize the AI HTML and wrap it in the basic mailing theme."""
        clean = html_sanitize(
            body,
            silent=False,
            sanitize_tags=True,
            sanitize_attributes=True,
            sanitize_style=True,
            sanitize_form=True,
            strip_classes=True,
        )
        root = lxml_html.fragment_fromstring(str(clean or ""), create_parent="div")
        dropped = 0
        # Comments survive the sanitizer and the mailing downloads images from
        # them on save; images could be trackers or become attachments.
        for node in root.xpath("//comment() | //img | //picture | //video | //audio"):
            node.drop_tree()
            dropped += 1
        for node in root.iter(etree.Element):
            for name in [n for n in node.attrib if n.startswith(("t-", "data-"))]:
                # The body is rendered as QWeb when it is sent.
                del node.attrib[name]
                dropped += 1
            if node.tag == "a":
                if not SAFE_HREF.match(node.get("href") or ""):
                    node.attrib.pop("href", None)
                node.set("target", "_blank")
            elif node.tag == "p" and not node.get("style"):
                node.set("style", "margin:0 0 12px 0;")
        inner = lxml_html.tostring(root, encoding="unicode")[
            len("<div>") : -len("</div>")
        ]
        if is_html_empty(inner):
            raise UserError(_("The body is empty once unsafe content is removed."))
        html = str(LAYOUT.format(content=Markup(inner), unsubscribe=_("Unsubscribe")))
        return html, dropped

    @api.model
    def _lab_cooling_rows(self, date_to, salesperson_ids):
        """The cooling companies of the catalogue tool, run as this user."""
        tool = self.env.ref(COOLING_TOOL, raise_if_not_found=False)
        if not tool:
            raise UserError(_("The tool pms_salesperson_cooling_customers is missing."))
        envelope = tool._execute_tool(
            date_to=date_to.isoformat(),
            salesperson_ids=salesperson_ids,
            top=COOLING_TOP,
        )
        rows, warnings = [], list(envelope.get("warnings") or [])
        for person in envelope["result"]["salespeople"]:
            if person["cooling_companies"] > len(person["top"]):
                warnings.append(
                    _(
                        "%(name)s: only the %(shown)s of %(total)s cooling companies "
                        "with most folios are considered."
                    )
                    % {
                        "name": person["salesperson"],
                        "shown": len(person["top"]),
                        "total": person["cooling_companies"],
                    }
                )
            rows += [
                dict(row, salesperson=person["salesperson"]) for row in person["top"]
            ]
        return rows, warnings

    @api.model
    def _lab_recipients(self, rows, max_recipients):  # noqa: C901 - one reason each
        partners = (
            self.env["res.partner"]
            .with_context(active_test=False)
            .search([("id", "in", [row["partner_id"] for row in rows])])
        )
        by_id = {partner.id: partner for partner in partners}
        emails = list({p.email_normalized for p in partners if p.email_normalized})
        Tools = self.env["pms.ai.tools"]
        blacklisted = opted_out = set()
        if emails:
            blacklisted = {
                row["email"]
                for row in Tools._ai_fetch(BLACKLIST_QUERY, {"emails": emails})
            }
            opted_out = {
                row["email_normalized"]
                for row in Tools._ai_fetch(OPTED_OUT_QUERY, {"emails": emails})
            }
        recipients, excluded, seen = [], [], set()
        for row in rows:
            partner = by_id.get(row["partner_id"])
            email = partner.email_normalized if partner else False
            if not partner:
                reason = _("not visible to you")
            elif not partner.active:
                reason = _("archived")
            elif partner.is_agency:
                reason = _("agency")
            elif not partner.email:
                reason = _("no email")
            elif not email:
                reason = (
                    _("email not normalized")
                    if email_normalize(partner.email, strict=False)
                    else _("invalid email")
                )
            elif email in blacklisted:
                reason = _("blacklisted")
            elif email in opted_out:
                reason = _("opted out")
            elif email in seen:
                reason = _("email used by another recipient")
            elif len(recipients) >= max_recipients:
                reason = _("over the limit")
            else:
                reason = None
            line = {
                "partner_id": row["partner_id"],
                "company": row.get("company"),
                "salesperson": row.get("salesperson"),
            }
            if reason:
                excluded.append(dict(line, reason=reason))
                continue
            seen.add(email)
            recipients.append(
                dict(
                    line,
                    email=email,
                    last_folio=row.get("last_folio"),
                    weeks_without_folios=row.get("weeks_without_folios"),
                    maybe_seasonal=row.get("maybe_seasonal"),
                )
            )
        return recipients, excluded

    @guarded_tool(
        input_schema={
            "date_to": DATE_TO_INPUT,
            "salesperson_ids": SALESPEOPLE_INPUT,
            "partner_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "maxItems": 200,
                "description": "Narrow the cooling companies to these.",
            },
            "subject": {"type": "string", "maxLength": 150},
            "preheader": {
                "type": "string",
                "maxLength": 200,
                "description": "Text shown next to the subject in the inbox.",
            },
            "body_html": {
                "type": "string",
                "maxLength": 20000,
                "description": "Simple HTML: paragraphs, bold, lists and https "
                "links. No images, scripts or {{ }}. Repeat it exactly when "
                "confirming.",
            },
            "mailing_name": {"type": "string", "maxLength": 100},
            "max_recipients": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_RECIPIENTS,
            },
        },
        output_schema={
            "mailing": {"type": "object"},
            "recipients": {"type": "array", "items": {"type": "object"}},
            "excluded": {"type": "array", "items": {"type": "object"}},
            "body_text": {"type": "string"},
        },
        required_inputs=["date_to", "salesperson_ids", "subject", "body_html"],
        write=True,
        apply="_ai_lab_reactivation_campaign_apply",
        # The recipients are company emails, some of self-employed people.
        log_result=False,
    )
    def _ai_lab_reactivation_campaign(
        self,
        date_to,
        salesperson_ids,
        subject,
        body_html,
        partner_ids=None,
        preheader=None,
        mailing_name=None,
        max_recipients=100,
    ):
        self._lab_check()
        if not self.env["mailing.mailing"].check_access_rights(
            "create", raise_exception=False
        ):
            raise AccessError(_("Preparing a mailing needs Email Marketing access."))
        if not self.env.user.email:
            raise UserError(_("Your user has no email: the mailing needs a sender."))
        subject = self._lab_plain_text(_("subject"), subject)
        preheader = self._lab_plain_text(_("preheader"), preheader)
        body, dropped = self._lab_clean_body(body_html)
        # The nested tool clears the cache: nothing built before it is kept.
        rows, warnings = self._lab_cooling_rows(date_to, salesperson_ids)
        excluded = []
        if partner_ids:
            listed = {row["partner_id"] for row in rows}
            excluded += [
                {
                    "partner_id": partner_id,
                    "company": None,
                    "salesperson": None,
                    "reason": _("not cooling"),
                }
                for partner_id in partner_ids
                if partner_id not in listed
            ]
            rows = [row for row in rows if row["partner_id"] in set(partner_ids)]
        recipients, more = self._lab_recipients(rows, max_recipients)
        excluded += more
        if dropped:
            warnings.append(
                _("%s unsafe or unsupported items were removed from the body.")
                % dropped
            )
        people = ", ".join(sorted({row["salesperson"] for row in rows}))
        mailing = {
            "name": f"{LAB_MARK} "
            + (
                mailing_name
                or _("Reactivation %(people)s %(date)s")
                % {"people": people, "date": date_to}
            ),
            "subject": subject,
            "preheader": preheader,
            "email_from": self.env.user.email_formatted,
            "recipients_model": "res.partner",
        }
        return {
            "summary": _(
                "Draft mailing for %(count)s companies (%(left)s left out). Nothing "
                "is sent: a person reviews and sends it from Email Marketing."
            )
            % {"count": len(recipients), "left": len(excluded)},
            "period": {"date_to": date_to},
            "definitions": [
                _(
                    "Recipients: the cooling companies of "
                    "pms_salesperson_cooling_customers (at most its 50 with most "
                    "folios per salesperson) that you can see, active, not agencies, "
                    "with a valid email that is not blacklisted, opted out or used "
                    "by another recipient."
                ),
                _("Odoo emails the company record itself, not its contacts."),
            ],
            "warnings": [
                _(
                    "Lab tool: only for staging. Do not press Test in Odoo: it would "
                    "render a real customer into the staging mail catcher, which "
                    "anyone can read."
                )
            ]
            + warnings,
            "result": {
                "mailing": mailing,
                "recipients": recipients,
                "excluded": excluded,
                "body_text": html2plaintext(body)[:1500],
            },
            "binding": {
                "mailing": mailing,
                "body": hashlib.sha256(body.encode()).hexdigest(),
                "recipients": [[row["partner_id"], row["email"]] for row in recipients],
                "excluded": [[row["partner_id"], row["reason"]] for row in excluded],
            },
            "plan": dict(
                mailing,
                body=body,
                partner_ids=[row["partner_id"] for row in recipients],
            ),
        }

    def _ai_lab_reactivation_campaign_apply(self, plan, **arguments):
        self._lab_check()
        if not plan["partner_ids"]:
            raise UserError(_("No company can receive the mailing: nothing created."))
        with lab_silence(self.env["mailing.mailing"]) as mailings:
            mailing = mailings.create(
                {
                    "name": plan["name"],
                    "subject": plan["subject"],
                    "preview": plan["preheader"] or False,
                    "mailing_type": "mail",
                    "mailing_model_id": self.env["ir.model"]._get_id("res.partner"),
                    "mailing_domain": repr(
                        [
                            ("id", "in", plan["partner_ids"]),
                            ("is_blacklisted", "=", False),
                        ]
                    ),
                    # The editor loads body_arch; body_html is what is sent
                    # until someone edits and saves it.
                    "body_arch": plan["body"],
                    "body_html": plan["body"],
                    "user_id": self.env.uid,
                }
            )
            mailing._message_log(
                body=Markup("<p>%s</p>")
                % _(
                    "Draft prepared by the AI lab (lab_reactivation_campaign); it "
                    "has not been sent."
                )
            )
        return {
            "summary": _(
                "Draft mailing %(name)s created for %(count)s companies; it has not "
                "been sent."
            )
            % {"name": mailing.name, "count": len(plan["partner_ids"])},
            "result": {
                "mailing_id": mailing.id,
                "name": mailing.name,
                "state": mailing.state,
                "recipients": len(plan["partner_ids"]),
                "email_from": mailing.email_from,
                "url": self._lab_url(mailing),
            },
        }
