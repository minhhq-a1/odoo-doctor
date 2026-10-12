from odoo import http
from odoo.http import request

REPORTS = {"xlsx": "report_xlsx", "pdf": "report_pdf"}


class Report(http.Controller):
    @http.route("/dd/download", type="http", auth="user")
    def download(self, res_id, res_model, method_print="report_xlsx"):
        record = request.env[res_model].browse(int(res_id))
        return getattr(record, method_print)()

    @http.route("/dd/safe", type="http", auth="user")
    def safe(self, res_id, res_model, kind):
        record = request.env[res_model].browse(int(res_id))
        return getattr(record, REPORTS[kind])()
