from odoo import models


class Variant(models.Model):
    _name = "x.variant"
    _description = "Variant"

    def copy(self, default=None):
        # copying a variant copies its template instead
        return self.mapped("template_id").copy(default=default)
