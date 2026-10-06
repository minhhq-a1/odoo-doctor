from odoo import http
from odoo.http import request
from odoo.tools import consteq


class Main(http.Controller):
    @http.route('/pr/base_url', auth='public')
    def base_url(self):
        # a constant config key read with sudo: nothing to report
        return request.env['ir.config_parameter'].sudo().get_param('web.base.url')

    @http.route('/pr/guarded/<int:rec_id>', auth='public')
    def guarded(self, rec_id, access_token=None):
        # sudo: the token below is the access check
        rec = request.env['res.partner'].sudo().browse(rec_id)
        if not consteq(rec.name or '', access_token or ''):
            raise request.not_found()
        return rec.name

    @http.route('/pr/open/<int:rec_id>', auth='public')
    def open(self, rec_id):
        # sudo: deliberately unchecked in this sample, the real finding
        return request.env['res.partner'].sudo().browse(rec_id).name
