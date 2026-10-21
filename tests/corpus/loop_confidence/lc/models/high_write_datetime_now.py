from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            ticket.write({"date_done": fields.Datetime.now(), "state": "done"})
