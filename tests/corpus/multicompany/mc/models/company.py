from odoo import fields, models


class Unprotected(models.Model):
    _name = "mc.unprotected"
    _description = "Company model without record rule"

    company_id = fields.Many2one("res.company", string="Company", required=True)


class Protected(models.Model):
    _name = "mc.protected"
    _description = "Company model with record rule"

    company_id = fields.Many2one("res.company", string="Company", required=True)
