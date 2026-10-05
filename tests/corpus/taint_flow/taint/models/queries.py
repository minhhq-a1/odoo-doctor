from odoo import models

TABLE = "res_partner"


class Queries(models.AbstractModel):
    _name = "taint.queries"
    _description = "Queries"

    # ---- provably constant: must NOT be reported ----------------------------
    def safe_placeholders(self, ids):
        marks = ",".join(["%s"] * len(ids))
        self.env.cr.execute(f"SELECT 1 FROM {TABLE} WHERE id IN ({marks})", ids)

    def safe_int_cast(self, limit):
        self.env.cr.execute(f"SELECT 1 FROM {TABLE} LIMIT {int(limit)}")

    def safe_fragments(self, flag, args):
        conds = []
        conds.append("a = %s")
        if flag:
            conds.append("b = %s")
        self.env.cr.execute("SELECT 1 FROM t WHERE " + " AND ".join(conds), args)

    def safe_branches(self, flag):
        query = "SELECT 1 FROM t" if flag else "SELECT 2 FROM t"
        self.env.cr.execute(query)

    def safe_eval_constant(self):
        expr = "1 + " + "2"
        return eval(expr)

    # ---- user data reaches SQL/eval: must be reported -----------------------
    def unsafe_parameter(self, name):
        self.env.cr.execute(f"SELECT 1 FROM t WHERE name = '{name}'")

    def unsafe_join(self, name):
        parts = ["SELECT 1 FROM t"]
        parts.append(f"WHERE name = '{name}'")
        self.env.cr.execute(" ".join(parts))

    def unsafe_branch(self, flag, x):
        if flag:
            query = f"SELECT 1 FROM t WHERE x = '{x}'"
        else:
            query = "SELECT 1 FROM t"
        self.env.cr.execute(query)

    def unsafe_eval(self, expr):
        return eval(expr)

    # ---- vetted by the developer: must NOT be reported ----------------------
    def vetted(self, where, args):
        # pylint: disable=sql-injection
        self.env.cr.execute(f"SELECT 1 FROM t WHERE {where}", args)
