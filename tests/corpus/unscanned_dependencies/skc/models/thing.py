from odoo import fields, models


class Thing(models.Model):
    _name = 'skc.thing'
    _description = 'Thing'

    name = fields.Char(string="Name")

    def action_open_alt(self):
        return {'view_id': self.env.ref('skc.thing_form_alt').id}


class StockMoveLine(models.Model):
    # core/enterprise model of an unscanned dependency: not a removed model
    _inherit = 'stock.move.line'


class Employee(models.Model):
    _inherit = 'hr.employee'


class LegacyInvoice(models.Model):
    # really removed in Odoo 13: must still be reported
    _inherit = 'account.invoice'
