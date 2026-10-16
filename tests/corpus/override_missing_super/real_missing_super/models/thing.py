from odoo import models


class Thing(models.Model):
    _name = "x.thing"
    _description = "Thing"

    def write(self, vals):
        self.env["x.log"].create({"note": "written"})
        return True

    def unlink(self):
        if not self:
            raise ValueError("nothing")
        self.env["x.log"].create({"note": "unlinked"})
        return True
