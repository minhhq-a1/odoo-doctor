from odoo import _, models
from odoo.exceptions import UserError


class Thing(models.Model):
    _name = "x.thing"
    _description = "Thing"

    def copy(self, default=None):
        raise UserError(_("You cannot duplicate a thing."))

    def write(self, vals):
        """Things are frozen."""
        raise UserError(_("Things are not meant to be written."))
