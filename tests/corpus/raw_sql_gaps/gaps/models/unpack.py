from odoo import models


class Unpack(models.AbstractModel):
    _name = "gaps.unpack"
    _description = "Taint through unpacking and walrus"

    def tuple_unpack(self, name):
        head, query = "x", f"SELECT id FROM res_partner WHERE name = '{name}'"
        self.env.cr.execute(query)

    def walrus(self, name):
        if (query := f"SELECT id FROM res_partner WHERE name = '{name}'"):
            self.env.cr.execute(query)
