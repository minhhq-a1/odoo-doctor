from psycopg2 import sql

from odoo import fields, models


class Safe(models.AbstractModel):
    _name = "prov.safe"
    _description = "Provenance that cannot inject: must stay silent"

    def limit_number(self, limit, offset):
        self.env.cr.execute("SELECT id FROM res_partner LIMIT %d" % limit)
        self.env.cr.execute("SELECT id FROM %s LIMIT %d OFFSET %i" % (self._table, limit, offset))
        self.env.cr.execute("SELECT id FROM res_partner LIMIT %(n)d" % {"n": limit})
        clause = "" if limit is None else " LIMIT %d" % limit
        self.env.cr.execute("SELECT id FROM res_partner" + clause)

    def query_object(self, domain):
        query = self._where_calc(domain)
        from_clause, where_clause, params = query.get_sql()
        self.env.cr.execute(f"SELECT id FROM {from_clause} WHERE {where_clause}", params)
        sql, params = self._where_calc(domain).subselect()
        self.env.cr.execute(f"SELECT id FROM res_partner WHERE id IN {sql}", params)
        sql, params = query.select("id", "SUM(x) AS total")
        self.env.cr.execute(f"SELECT * FROM ({sql}) t", params)

    def checked_choice(self, operator, operand):
        if operator not in ("<", "=", ">"):
            return []
        self.env.cr.execute(f"SELECT id FROM res_partner WHERE x {operator} %s", (operand,))

    def ids_and_clock(self, team):
        cond = f"team_id = {team.id} AND write_date > '{fields.Datetime.now()}'"
        self.env.cr.execute("SELECT id FROM crm_lead WHERE " + cond)

    def composed(self, search):
        query = sql.SQL("SELECT id FROM {table} WHERE name ILIKE {search}").format(
            table=sql.Identifier(self._table), search=sql.Placeholder("search")
        )
        self.env.cr.execute(query, {"search": search})
