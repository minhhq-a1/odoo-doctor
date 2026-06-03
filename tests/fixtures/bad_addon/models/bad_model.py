from odoo import api, fields, models


class BadModel(models.Model):
    _name = "bad.model"
    _description = "Bad Model with issues"

    name = fields.Char(required=True)
    partner_id = fields.Many2one("res.partner", string="Partner")

    def bad_sql_method(self):
        """Raw SQL with f-string — triggers raw-sql-string-interpolation."""
        table = "sale_order"
        self.env.cr.execute(f"SELECT * FROM {table}")

    def also_bad_sql(self):
        """Raw SQL with % formatting — also bad."""
        name = "test"
        self.env.cr.execute("SELECT * FROM res_partner WHERE name = '%s'" % name)

    def good_method(self):
        """Normal method — no issues."""
        return self.search([("name", "!=", False)])
