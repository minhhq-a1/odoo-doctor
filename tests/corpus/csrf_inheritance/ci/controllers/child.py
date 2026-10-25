from odoo import http
from odoo.addons.ci.controllers.base import Base
from odoo.addons.elsewhere.controllers.main import Other


class PublicOverride(Base):
    # keeps auth='public' of the parent: a webhook, not a session route
    @http.route(methods=["POST"], csrf=False)
    def hook(self):
        return super().hook()


class UserOverride(Base):
    # keeps auth='user': still a logged-in route without CSRF
    @http.route(methods=["POST"], csrf=False)
    def form(self):
        return super().form()


class UnknownParent(Other):
    # the parent route is not in the scanned code: cannot tell
    @http.route("/ci/other", methods=["POST"], csrf=False)
    def other(self):
        return "ok"


class NewRoute(http.Controller):
    @http.route("/ci/new", methods=["POST"], csrf=False)
    def new(self):
        return "ok"
