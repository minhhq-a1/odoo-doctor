from odoo import http
from odoo.http import request


class Main(http.Controller):
    @http.route("/gaps/search", auth="public")
    def search(self, name):
        request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{name}'")
        request.cr.execute("SELECT id FROM res_partner WHERE name = '%s'" % name)
        return "ok"

    @http.route("/gaps/safe", auth="public")
    def safe(self, name):
        request.env.cr.execute("SELECT id FROM res_partner WHERE name = %s", (name,))
        return "ok"
