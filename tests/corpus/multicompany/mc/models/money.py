from odoo import fields, models


class BadInvoice(models.Model):
    _name = "mc.bad.invoice"
    _description = "Invoice without currency"

    amount = fields.Monetary(string="Amount")


class GoodInvoice(models.Model):
    _name = "mc.good.invoice"
    _description = "Invoice with currency"

    currency_id = fields.Many2one("res.currency", string="Currency", required=True)
    amount = fields.Monetary(string="Amount")
