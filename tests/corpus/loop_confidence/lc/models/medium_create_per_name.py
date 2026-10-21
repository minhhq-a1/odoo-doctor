from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self, names):
        for name in names:
            self.env["lc.ticket"].create({"name": name})
