from odoo import fields, models


class MfThing(models.Model):
    _name = "mf.thing"
    _description = "Migration fix sample"

    name = fields.Char(string="Name", required=True)
    # the chatter fields of mail.thread, declared here so the sample needs no dependency
    message_ids = fields.One2many("mail.message", "res_id")
    message_follower_ids = fields.One2many("mail.followers", "res_id")

    def open_list(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "mf.thing",
            "view_mode": "tree,form",
        }

    def open_ok(self):
        return {"view_mode": "tree,form", "note": "not an action: no type, no res_model"}

    def pairs(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "mf.thing",
            "views": [(False, "tree"), (False, "form")],
        }
