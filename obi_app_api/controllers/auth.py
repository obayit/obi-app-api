from pprint import pprint
from odoo import models, http, _
from odoo.http import request
from odoo.exceptions import UserError
import odoo.models as odoo_models
from odoo.osv import expression


class AuthController(http.Controller):
    @http.route([
        '/obi_app/signup',
    ], auth='public', type='json')
    def app_singup(self, *args, **kwargs):
        # todo: test this on multi database instance!
        self.do_signup(kwargs)

        # mfa is not supported by this api, no need
        # Set user to public if they were not signed in by do_signup
        # (mfa enabled)
        # if request.session.uid is None:
        #     public_user = request.env.ref('base.public_user')
        #     request.update_env(user=public_user)

        # Send an account creation confirmation email
        User = request.env['res.users']
        user_sudo = User.sudo().search(
            User._get_login_domain(kwargs.get('login')), order=User._get_login_order(), limit=1
        )
        template = request.env.ref('auth_signup.mail_template_user_signup_account_created', raise_if_not_found=False)
        if user_sudo and template:
            template.sudo().send_mail(user_sudo.id, force_send=True)

        return request.env['ir.http'].session_info()  # the same return as the endpoint /web/session/login

    def _prepare_signup_values(self, qcontext):
        values = { key: qcontext.get(key) for key in ('login', 'name', 'password') }
        if not values:
            raise UserError(_("The form was not properly filled in."))
        if values.get('password') != qcontext.get('confirm_password'):
            raise UserError(_("Passwords do not match; please retype them."))
        supported_lang_codes = [code for code, _ in request.env['res.lang'].get_installed()]
        lang = request.context.get('lang', '')
        if lang in supported_lang_codes:
            values['lang'] = lang
        return values

    def do_signup(self, request_params):
        """ Shared helper that creates a res.partner out of a token """
        values = self._prepare_signup_values(request_params)
        self._signup_with_values(values)
        request.env.cr.commit()

    def _signup_with_values(self, values):
        login, password = request.env['res.users'].sudo().signup(values)
        request.env.cr.commit()     # as authenticate will use its own cursor we need to commit the current transaction
        pre_uid = request.session.authenticate(request.db, login, password)
        if not pre_uid:
            raise UserError(_('Authentication Failed.'))
