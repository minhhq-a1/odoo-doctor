from odoo import models
from odoo.tools import SQL


class QuerySinks(models.AbstractModel):
    _name = "prov.query.sinks"
    _description = "env.execute_query and copy_expert are SQL sinks too"

    def wrapped(self, name):
        self.env.execute_query(SQL(f"SELECT id FROM res_partner WHERE name = '{name}'"))

    def copy_out(self, name):
        self.env.cr.copy_expert(f"COPY (SELECT id FROM res_partner WHERE name = '{name}') TO STDOUT", None)

    def bound(self, name):
        self.env.execute_query(SQL("SELECT id FROM res_partner WHERE name = %s", name))

    def constant(self):
        self.env.execute_query(SQL("SELECT 1"))

    def not_a_cursor(self, name):
        self.client.execute_query(f"SELECT {name}")
