from odoo import fields, models


class Ticket(models.Model):
    _name = "lc.ticket"
    _description = "Ticket"

    name = fields.Char()
    state = fields.Char()
    count = fields.Integer()
