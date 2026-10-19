from odoo import http
from odoo.http import request


class Base(http.Controller):
    @http.route("/ci/pub", auth="public")
    def pub(self):
        return "ok"

    @http.route("/ci/pub2", auth="public")
    def pub2(self):
        return "ok"

    @http.route("/ci/priv", auth="user")
    def priv(self, rec_id=0):
        return "ok"

    @http.route("/ci/own", auth="user")
    def own(self, rec_id=0):
        return "ok"
