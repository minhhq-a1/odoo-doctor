import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)
ALLOWED = {"confirm", "cancel"}


class Step(models.Model):
    _name = "dd.step"
    _description = "Step"

    callback = fields.Char()

    def run_stored(self):
        # the name is stored data, not what a caller sends: medium
        for step in self:
            getattr(self, step.callback)()

    def run_checked(self, name):
        if name not in ALLOWED:
            raise ValueError(name)
        return getattr(self, name)()

    def run_prefixed(self, kind):
        return getattr(self, "_do_%s" % kind)()

    def log(self, level, message):
        getattr(_logger, level)(message)
