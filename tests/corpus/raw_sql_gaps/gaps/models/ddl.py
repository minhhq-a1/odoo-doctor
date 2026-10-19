from odoo import models


class Ddl(models.AbstractModel):
    _name = "gaps.ddl"
    _description = "DDL built with format()"

    def drop(self, table):
        self.env.cr.execute("DROP TABLE {}".format(table))

    def alter(self, table):
        self.env.cr.execute("ALTER TABLE {} ADD COLUMN x int".format(table))

    def truncate(self, table):
        self.env.cr.execute("TRUNCATE {}".format(table))

    def pooled(self, name):
        with self.pool.cursor() as new_cr:
            new_cr.execute(f"SELECT id FROM res_partner WHERE name = '{name}'")
