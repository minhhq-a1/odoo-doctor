from odoo import models


class Reachable(models.AbstractModel):
    _name = "prov.reachable"
    _description = "A parameter a caller controls reaches the SQL: high"

    def public_param(self, name):
        self.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{name}'")

    def beside_metadata(self, name):
        self.env.cr.execute(f"SELECT {self._cols()} FROM {self._table} WHERE name = '{name}'")

    def text_beside_number(self, name, limit):
        self.env.cr.execute("SELECT id FROM res_partner WHERE name = '%s' LIMIT %d" % (name, limit))

    def through_locals(self, name):
        parts = ["SELECT id FROM res_partner"]
        parts.append("WHERE name = '" + name + "'")
        self.env.cr.execute(" ".join(parts))

    def inner_function(self, name):
        def run():
            self.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{name}'")

        run()
