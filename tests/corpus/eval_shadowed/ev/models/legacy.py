from odoo import models
from odoo.tools.safe_eval import safe_eval as eval  # Odoo 8/9 idiom kept in a port


class Legacy(models.AbstractModel):
    _name = 'ev.legacy'
    _description = 'Legacy'

    def run(self, expr):
        return eval(expr)  # sandboxed safe_eval, not the builtin
