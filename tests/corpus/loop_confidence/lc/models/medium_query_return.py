from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            found = self.env["lc.ticket"].search([("state", "=", "new")])
            if found:
                return found
