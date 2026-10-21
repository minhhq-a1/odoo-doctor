from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            self._close(ticket)
            self.env["lc.ticket"].search([("state", "=", "new")])
