from odoo import fields, models


class Thing(models.Model):
    _name = "shop.thing"
    _description = "Thing"

    name = fields.Char(string="Name")
