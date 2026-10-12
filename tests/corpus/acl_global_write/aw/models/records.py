from odoo import fields, models


class Open(models.Model):
    _name = "aw.open"
    _description = "Writable by everyone"

    name = fields.Char()


class Form(models.Model):
    _name = "aw.form"
    _description = "Public form"

    name = fields.Char()


class Safe(models.Model):
    _name = "aw.safe"
    _description = "Grouped"

    name = fields.Char()


class Wizard(models.TransientModel):
    _name = "aw.wizard"
    _description = "Wizard"

    name = fields.Char()
