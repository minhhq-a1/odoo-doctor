from odoo import api, fields, models


class ResCore(models.Model):
    _name = "res.core"
    _description = "Core"

    name = fields.Char()
    # Odoo 19 style: a type annotation on the field
    parent_id: "ResCore" = fields.Many2one("res.core", ondelete="cascade")
    child_ids = fields.One2many("res.core", "parent_id")
    image = fields.Image()
    payload = fields.Json()
    line_ids = fields.One2many("res.core.line", "core_id")
    child_count = fields.Integer(compute="_compute_child_count")
    child_count_text = fields.Char(compute="_compute_child_count")
    parent_name = fields.Char(related="parent_id.name")
    parent_ref = fields.Many2one(related="parent_id.parent_id")

    @api.depends("child_ids")
    def _compute_child_count(self):
        for rec in self:
            # `child_count` is this method's own result: reading it back is not an input
            rec.child_count = len(rec.child_ids)
            rec.child_count_text = str(rec.child_count)


class ResCoreLine(models.Model):
    _name = "res.core.line"
    _description = "Core line"

    core_id = fields.Many2one(
        "res.core", string="Core", required=True, ondelete="cascade"
    )
    qty = fields.Float()
