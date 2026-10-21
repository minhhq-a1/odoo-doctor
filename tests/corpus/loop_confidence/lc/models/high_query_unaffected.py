from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        counts = []
        for ticket in self:
            tags = self.env["lc.ticket"].search([("state", "=", "new")])
            counts.append(len(tags))
