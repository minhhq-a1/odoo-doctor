from odoo import http
from odoo.http import request

from odoo.addons.ci.controllers.base import Base


class Child(Base):
    # no auth here: the route keeps auth='public' from Base.pub
    @http.route()
    def pub(self):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")

    # a new path and website=True still keep Base.pub2's auth='public'
    @http.route("/ci/pub2/new", website=True)
    def pub2(self):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")

    # inherits auth='user': not a public route
    @http.route()
    def priv(self, rec_id=0):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")


class GrandChild(Child):
    # two levels below Base.pub: still public
    @http.route()
    def pub(self):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")

    # auth='user' is on the route and wins over what the parent says
    @http.route("/ci/pub2/user", auth="user")
    def pub2(self):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")


class Own(http.Controller):
    # nothing to inherit: the default auth is 'user'
    @http.route("/ci/own/route")
    def route(self):
        return request.env["res.partner"].sudo().search([], limit=5).mapped("name")


class Closer(Base):
    # a route of an authenticated parent: a caller-chosen id is elevated and changed
    @http.route()
    def priv(self, rec_id=0):
        request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})

    # explicit auth: rpc-sudo-without-access-check still sees it
    @http.route("/ci/closer/explicit", auth="user")
    def explicit(self, rec_id=0):
        request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})

    @http.route("/ci/closer/checked", auth="user")
    def checked(self, rec_id=0):
        rec = request.env["res.partner"].browse(rec_id)
        rec.check_access("write")
        rec.sudo().write({"name": "x"})


class Chain(Closer):
    # priv resolves to 'user' through Closer and Base
    @http.route()
    def priv(self, rec_id=0):
        request.env["res.partner"].sudo().browse(rec_id).write({"name": "y"})


class Pubby(Base):
    # public: left to public-controller-sudo-risk, not reported twice
    @http.route("/ci/pubby", auth="public")
    def pubby(self, rec_id=0):
        request.env["res.partner"].sudo().browse(rec_id).write({"name": "x"})
