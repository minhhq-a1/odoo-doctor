from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self, names):
        while names:
            self.env["lc.ticket"].search([("state", "=", "new")])
            names.pop()
