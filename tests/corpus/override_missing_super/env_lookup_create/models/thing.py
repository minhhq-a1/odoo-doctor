from odoo import api, models


class Thing(models.Model):
    _name = "x.thing"
    _description = "Thing"

    @api.model_create_multi
    def create(self, vals_list):
        return self.env["x.other"].create(vals_list)

    def write(self, vals):
        return self.with_context(skip=True).write(vals)

    def unlink(self):
        other = self.env["x.other"].browse(1)
        return other.unlink()
