from odoo import http


class Base(http.Controller):
    @http.route("/ci/hook", auth="public", methods=["POST"], csrf=False)
    def hook(self):
        return "ok"

    @http.route("/ci/form", auth="user", methods=["POST"], csrf=False)
    def form(self):
        return "ok"
