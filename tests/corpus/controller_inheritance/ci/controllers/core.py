from odoo import http
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.website_sale.controllers.main import WebsiteSale


class Shop(WebsiteSale):
    # WebsiteSale is not in the scanned project: the auth of the parent route is unknown
    @http.route()
    def shop(self, **kwargs):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")

    @http.route()
    def cart(self, access_token=None, **kwargs):
        partner = request.env["res.partner"].sudo().browse(1)
        if not consteq(partner.name or "", access_token or ""):
            raise request.not_found()
        return partner.name

    @http.route("/ci/shop/user", auth="user")
    def shop_user(self, **kwargs):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")


class Portal(CustomerPortal):
    # a controller whose base is not named Controller: a caller-chosen id is elevated
    @http.route("/my/ci/<int:rec_id>", auth="user")
    def my_ci(self, rec_id):
        request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})

    @http.route("/my/ci/checked/<int:rec_id>", auth="user")
    def my_ci_checked(self, rec_id):
        rec = request.env["res.partner"].browse(rec_id)
        rec.check_access("write")
        rec.sudo().write({"name": "x"})

    # the parent route is out of sight: no claim about its auth, no rpc finding
    @http.route()
    def home(self, rec_id=0, **kwargs):
        request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})
