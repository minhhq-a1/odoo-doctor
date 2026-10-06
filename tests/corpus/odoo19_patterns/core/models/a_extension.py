from odoo import fields, models


class CoreExtension(models.Model):
    _inherit = "res.core"

    ext_note = fields.Char()
