from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            self.env["lc.ticket"].search([("name", "=", ticket.name)])
