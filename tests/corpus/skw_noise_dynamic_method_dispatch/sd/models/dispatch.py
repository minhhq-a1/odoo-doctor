import functools

from odoo import fields, models


class Handler(models.Model):
    _name = "sd.handler"
    _description = "Handler"

    kind = fields.Char()
    callback = fields.Char()

    def store_values(self):
        # The names come from a literal tuple, so the code fixes them.
        candidates = ("_values_for_" + self.kind, "_values")
        for candidate in candidates:
            handler = getattr(self, candidate, None)
            if handler is not None:
                handler()

    def wrap(self, origin):
        @functools.wraps(origin)
        def wrapper(rec, *args, **kwargs):
            # The name is the decorated function's own name.
            method_name = origin.__name__
            options_method = getattr(rec, f"{method_name}_options", None)
            options = options_method() if options_method else {}
            return getattr(rec, method_name)(*args, **kwargs), options

        return wrapper

    def _callback_method(self, record, name):
        name = (name or "").strip()
        if not name or name.startswith("_") or hasattr(models.BaseModel, name):
            return None
        return getattr(record, name, None)

    def run_buttons(self, record):
        for button in (self.callback or "").split(","):
            parts = button.split("-")
            if self._callback_method(record, parts[1]):
                getattr(record, parts[1].strip())()

    def run_stored(self):
        # Still reported (medium): a name stored on a record, nothing checks it.
        for rec in self:
            getattr(rec, rec.callback)()

    def run_public(self, method_name):
        # Still reported (high): the caller picks the method.
        return getattr(self, method_name)()


class Proxy:
    def __init__(self, target):
        self.target = target

    def __getattr__(self, name):
        def call(*args, **kwargs):
            return getattr(self.target, name)(*args, **kwargs)

        return call
