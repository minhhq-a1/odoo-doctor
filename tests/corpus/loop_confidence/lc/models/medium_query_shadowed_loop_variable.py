from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self, others):
        for ticket in self:
            self.env["lc.ticket"].search(
                [("id", "=", ticket.id), ("id", "in", [ticket for ticket in others])]
            )
