from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self, names):
        for _name in names:
            self.env["lc.ticket"].create({"state": "new"})
