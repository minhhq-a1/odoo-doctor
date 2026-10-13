from odoo import http


class Main(http.Controller):
    @http.route("/br/save", type="http", auth="user", methods=["POST"], csrf=False)
    def save(self, **kw):  # true positive: session auth without a CSRF token
        return "ok"

    @http.route("/br/hook", type="http", auth="public", methods=["POST"], csrf=False)
    def hook(self, **kw):  # webhook: fine
        return "ok"

    @http.route("/br/view", type="http", auth="user", methods=["GET"], csrf=False)
    def view(self, **kw):  # GET is never checked: fine
        return "ok"

    @http.route("/br/rpc", type="jsonrpc", auth="user", csrf=False)
    def rpc(self, **kw):  # JSON routes are not covered by the check: fine
        return {}
