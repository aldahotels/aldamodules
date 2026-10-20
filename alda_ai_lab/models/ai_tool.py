from odoo import _, models
from odoo.exceptions import UserError

from .lab import LAB_MODEL_PREFIX, lab_enabled


class AiTool(models.Model):
    _inherit = "ai.tool"

    def _alda_ai_lab_tool(self):
        self.ensure_one()
        return (self.sudo().model_id.model or "").startswith(LAB_MODEL_PREFIX)

    def _pms_ai_is_allowed(self):
        # Outside the lab the tools are not even listed.
        if self._alda_ai_lab_tool() and not lab_enabled(self.env):
            return False
        return super()._pms_ai_is_allowed()

    def _execute_tool(self, *args, record=None, **kwargs):
        self.ensure_one()
        if self._alda_ai_lab_tool() and not lab_enabled(self.env):
            raise UserError(_("The lab tool %s only runs on staging.") % self.name)
        return super()._execute_tool(*args, record=record, **kwargs)
