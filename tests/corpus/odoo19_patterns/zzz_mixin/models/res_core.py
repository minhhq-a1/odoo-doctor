from odoo import fields, models


class ResCore(models.Model):
    _name = "res.core"
    _inherit = ["res.core", "mail.thread"]

    mixin_flag = fields.Boolean()
