from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            ticket.write({"state": "done"})
            ticket.message_post(body="done")
