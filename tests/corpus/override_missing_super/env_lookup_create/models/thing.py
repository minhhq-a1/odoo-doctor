from odoo import api, models


class Thing(models.Model):
    _name = "x.thing"
    _description = "Thing"

    @api.model_create_multi
    def create(self, vals_list):
        return self.env["x.other"].create(vals_list)
