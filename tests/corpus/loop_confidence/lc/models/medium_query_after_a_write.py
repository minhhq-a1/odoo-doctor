from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            ticket.write({"state": "done"})
            self.env["lc.ticket"].search([("state", "=", "done")])
