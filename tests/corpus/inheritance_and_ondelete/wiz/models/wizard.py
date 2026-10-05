from odoo import fields, models


class Parent(models.TransientModel):
    _name = "parent.wiz"
    _description = "Parent wizard"

    job_ids = fields.Many2many("res.partner", string="Jobs")

    def action_parent(self):
        return True


class Child(models.TransientModel):
    _inherit = "parent.wiz"
    _name = "child.wiz"
    _description = "Child wizard"


class Ticket(models.Model):
    _name = "wiz.ticket"
    _description = "Ticket"

    owner_id = fields.Many2one("res.users", string="Owner", required=True)
    partner_id = fields.Many2one("res.partner", string="Partner")
