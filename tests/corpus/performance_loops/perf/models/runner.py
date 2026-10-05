from odoo import models


class Runner(models.Model):
    _name = "perf.runner"
    _description = "Runner"

    def run(self, ids, vals):
        for i in ids:
            self.env["res.partner"].browse(i)
        for v in vals:
            self.env["res.partner"].search([("id", "=", v)])
            self.env["res.partner"].create({"name": v})
