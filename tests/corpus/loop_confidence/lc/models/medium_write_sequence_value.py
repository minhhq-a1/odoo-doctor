from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            ticket.write({"name": self.env["ir.sequence"].next_by_code("lc.ticket")})
