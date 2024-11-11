##############################################################################
#    License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
#    Copyright (C) 2023 Comunitea Servicios Tecnológicos S.L. All Rights Reserved
#    Vicente Ángel Gutiérrez <vicente@comunitea.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import json
import werkzeug
from odoo import http, _
from odoo.http import request
from werkzeug.exceptions import BadRequest, Unauthorized

from odoo.addons.portal.controllers import portal
from odoo.addons.web.controllers.main import Home
from odoo.addons.web.controllers.main import ensure_db

class BlockHome(Home):
    @http.route('/web', type='http', auth="none")
    def web_client(self, s_action=None, **kw):
        if request.session.uid and request.env['res.users'].sudo().browse(request.session.uid).has_group('custom_pos_pms_link.group_user_no_backend'):
            return http.local_redirect('/my', query=request.params, keep_hash=True)
        return super(BlockHome, self).web_client(s_action, **kw)

class CustomerPortal(portal.CustomerPortal):
    @http.route(['/pos_login_by_token/<int:user_id>'], type='http', auth="public", website=True)
    def portal_pos_login_by_token(self, user_id=None, access_token=None, **kw):
        #localhost:14069/pos_login_by_token/381?signup_token=1LCzJ80sGoNu4ODEBl5C&config_id=1
        ensure_db()
        signup_token = kw.get('signup_token', False)
        config_id = kw.get('config_id', False)

        if not user_id or not signup_token:
            raise Unauthorized("Wrong authentication")
        
        portal_user = request.env['res.users'].sudo().browse(user_id)

        if portal_user:
            cur_user = request.env['res.users'].browse(request.env.uid)
            is_public = cur_user._is_public()
            if (is_public or cur_user.id != portal_user.id) and signup_token == portal_user.signup_token:
                request.session.logout(keep_db=True)
                request.session.authenticate(request.db, portal_user.login, signup_token)
        url = "/pos/ui?config_id={}".format(config_id)
        return werkzeug.utils.redirect(url)

class SessionController(http.Controller):
    @http.route(
        "/open_pos_session/<int:config_id>", type="json", auth="public", csrf=False,
    )
    def portal_open_pos_session(self, config_id="", access_token=None, **kw):
        try:
            config_id = request.env["pos.config"].sudo().browse(config_id)
            if not config_id:
                raise BadRequest("Configuration not found")
            if config_id.current_session_id:
                raise BadRequest("There is already an open session")
            cash_register_id = http.request.jsonrequest.get('cash_register_id', False)
            ctx = dict(request.context)
            ctx.update({"cash_register_id": cash_register_id})
            session = config_id.with_context(ctx).get_pos_session()
            return json.dumps(
                {
                    "result": True,
                    "session": session,
                    "message": _("Session opened successfully."),
                }
            )
        except Exception as e:
            return json.dumps({"result": False, "message": str(e)})
    
    @http.route(
        "/close_pos_session/<int:config_id>", type="json", auth="public", csrf=False,
    )
    def portal_close_pos_session(self, config_id="", access_token=None, **kw):
        try:
            config_id = request.env["pos.config"].sudo().browse(config_id)
            if not config_id:
                raise BadRequest("Configuration not found")
            if not config_id.current_session_id:
                raise BadRequest("There is no open session")
            config_id.current_session_id.action_pos_session_closing_control()
            return json.dumps(
                {
                    "result": True,
                    "message": _("Session closed successfully."),
                }
            )
        except Exception as e:
            return json.dumps({"result": False, "message": str(e)})
