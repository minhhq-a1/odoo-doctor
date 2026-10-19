from odoo import models
from odoo.tools import SQL


class SqlWrapper(models.AbstractModel):
    _name = "gaps.sql.wrapper"
    _description = "SQL() wrapped around a built string"

    def fstring(self, name):
        self.env.cr.execute(SQL(f"SELECT id FROM res_partner WHERE name = '{name}'"))

    def concatenation(self, name):
        self.env.cr.execute(SQL("SELECT id FROM res_partner WHERE name = '" + name + "'"))

    def formatted(self, name):
        self.env.cr.execute(SQL("SELECT id FROM res_partner WHERE name = '{}'".format(name)))

    def percent(self, name):
        self.env.cr.execute(SQL("SELECT id FROM res_partner WHERE name = '%s'" % name))
