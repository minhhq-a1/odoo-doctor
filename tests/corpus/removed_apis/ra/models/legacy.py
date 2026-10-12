from odoo import api, fields, models


class Mixin:
    # A plain Python mixin: not a model, so not reported.
    _sql_constraints = [("m_uniq", "unique(name)", "Name must be unique")]


class Legacy(models.Model):
    _name = "ra.legacy"
    _description = "Legacy"

    name = fields.Char()

    # Odoo 19 no longer reads this: the constraint is never created.
    _sql_constraints = [("name_uniq", "unique(name)", "Name must be unique")]

    def name_get(self):
        return [(r.id, r.name) for r in self]

    @api.model
    def fields_view_get(self, view_id=None, view_type="form", **kwargs):
        return super().fields_view_get(view_id, view_type, **kwargs)

    def refresh(self):
        self.env["ra.legacy"].invalidate_cache()


class Modern(models.Model):
    _name = "ra.modern"
    _description = "Modern"

    name = fields.Char()

    _name_uniq = models.Constraint("UNIQUE(name)", "Name must be unique")
    _sql_constraints = []

    def name_get_label(self):
        return self.display_name
