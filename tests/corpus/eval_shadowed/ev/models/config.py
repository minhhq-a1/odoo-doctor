from odoo import fields, models


class Config(models.AbstractModel):
    _name = 'ev.config'
    _description = 'Config'

    condition = fields.Char(string="Condition")

    def check(self):
        return eval(self.condition)  # the builtin on an editable field: real finding
