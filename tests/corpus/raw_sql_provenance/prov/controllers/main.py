from odoo import http


class Main(http.Controller):
    @http.route("/prov/find", auth="public")
    def find(self, term):
        http.request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{term}'")
        return "ok"

    @http.route("/prov/hidden", auth="public")
    def _hidden(self, term):
        http.request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{term}'")
        return "ok"
