from odoo import api, fields, models


class SaleOrderCustom(models.Model):
    _inherit = "sale.order"

    custom_note = fields.Text(string="Custom Note")
    total_weight = fields.Float(compute="_compute_total_weight", store=True)

    @api.depends("order_line.product_id")
    def _compute_total_weight(self):
        for order in self:
            order.total_weight = sum(
                line.product_id.weight for line in order.order_line
            )

    def action_confirm_custom(self):
        self.ensure_one()
        return self.action_confirm()


class SaleCustomWizard(models.TransientModel):
    _name = "sale.custom.wizard"
    _description = "Sale Custom Wizard"

    name = fields.Char(required=True)
