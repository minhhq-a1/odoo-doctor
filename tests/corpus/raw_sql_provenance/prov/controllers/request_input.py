from odoo import http
from odoo.http import request


class RequestInput(http.Controller):
    @http.route("/prov/params", auth="public")
    def params(self):
        request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{request.params['q']}'")

    @http.route("/prov/args", auth="public")
    def args(self):
        term = request.httprequest.args.get("q")
        request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{term}'")

    @http.route("/prov/json", auth="public", type="json")
    def json_body(self):
        data = request.get_json_data()
        request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{data['q']}'")

    @http.route("/prov/alias", auth="public")
    def alias(self):
        http.request.env.cr.execute(
            f"SELECT id FROM res_partner WHERE name = '{http.request.params.get('q')}'"
        )

    @http.route("/prov/post", auth="public")
    def post(self, **post):
        request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{post['q']}'")

    @http.route("/prov/hop", auth="public")
    def hop(self, term):
        return self._search(term)

    def _search(self, term):
        request.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{term}'")

    @http.route("/prov/literal", auth="public")
    def literal(self):
        return self._run("res_partner")

    def _run(self, table):
        request.env.cr.execute(f"SELECT id FROM {table}")
