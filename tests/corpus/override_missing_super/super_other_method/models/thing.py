from odoo import api, models


class Thing(models.Model):
    _name = "x.thing"
    _description = "Thing"

    @api.model_create_multi
    def create(self, vals_list):
        # super().write() is not the create chain: nothing is ever inserted
        self.env["x.log"].browse(1).write({"note": "created"})
        super().write({})
        return self

    def write(self, vals):
        return super(Thing, self).write(vals)

    def unlink(self):
        parent = super()
        return parent.unlink()

    def copy(self, default=None):
        res = super().copy_data(default)
        return self.browse()
