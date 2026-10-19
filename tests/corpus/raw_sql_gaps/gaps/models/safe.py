from odoo import models
from odoo.tools import SQL


class Safe(models.AbstractModel):
    _name = "gaps.safe"
    _description = "Forms that must stay silent"

    def bound_sql(self, name, table):
        self.env.cr.execute(SQL("SELECT id FROM res_partner WHERE name = %s", name))
        self.env.cr.execute(SQL("SELECT id FROM %s", SQL.identifier(table)))
        self.env.cr.execute(SQL("SELECT 1"))

    def placeholders(self, ids):
        marks = ",".join(["%s"] * len(ids))
        self.env.cr.execute("SELECT id FROM res_partner WHERE id IN (" + marks + ")", ids)

    def unpacked_constants(self, name):
        head, query = "x", "SELECT id FROM res_partner WHERE name = %s"
        self.env.cr.execute(query, (name,))

    def walrus_constant(self, name):
        if (query := "SELECT id FROM res_partner WHERE name = %s"):
            self.env.cr.execute(query, (name,))

    def not_a_cursor(self, job, name):
        job.execute(f"DROP the old {name}")

    def not_sql(self, name):
        self.env.cr.execute("hello {}".format(name))
