from odoo import fields, models


class MgThing(models.Model):
    _name = "mg.thing"
    _description = "Migration sample"

    name = fields.Char(string="Name", required=True)
    # A model of the module's own may name a field groups_id: not a reference to the old one.
    groups_id = fields.Many2many("res.groups")

    def open_list(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "mg.thing",
            "view_mode": "tree,form",  # true positive
            "target": "inline",  # true positive
        }

    def open_ok(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "mg.thing",
            "view_mode": "list,form",
            "target": "new",
        }

    def compat(self, user):
        return "groups_id" in user._fields  # a version probe: fine
