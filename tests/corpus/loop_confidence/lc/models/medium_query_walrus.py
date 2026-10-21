from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            current = (state := ticket.state)
            self.env["lc.ticket"].search([("state", "=", state)])
