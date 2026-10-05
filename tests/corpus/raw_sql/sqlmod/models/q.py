from odoo import models


class Q(models.AbstractModel):
    _name = "sql.q"
    _description = "Q"

    def vetted(self, where, args):
        # pylint: disable=sql-injection
        # values are bound through args
        self.env.cr.execute(f"SELECT 1 FROM t WHERE {where}", args)

    def unvetted(self, where, args):
        self.env.cr.execute(f"SELECT 2 FROM t WHERE {where}", args)

    def parameterised(self, name):
        self.env.cr.execute("SELECT 3 FROM t WHERE name = %s", (name,))
