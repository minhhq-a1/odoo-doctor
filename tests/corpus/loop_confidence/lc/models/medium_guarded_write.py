from odoo import fields, models


class Ticket(models.Model):
    _inherit = "lc.ticket"

    def run(self):
        for ticket in self:
            if ticket.state == "draft":
                ticket.write({"state": "done"})
