from odoo import models


class Convention(models.AbstractModel):
    _name = "prov.convention"
    _description = "Dynamic SQL the way Odoo's own addons write it: medium"

    def _update_column(self, column):
        # private helper: every caller is inside the module
        self.env.cr.execute(f"UPDATE res_company SET {column} = true")

    def seen(self):
        # fragments built by methods of the model
        join, where = self._seen_extra()
        query = "SELECT 1 FROM %(table)s t %(join)s WHERE %(where)s"
        self.env.cr.execute(query % {"table": self._table, "join": join, "where": where})

    def last(self):
        self.env.cr.execute(f"SELECT {self._sequence_field} FROM {self._table} {self._where()}")

    def only_cast(self, n):
        self.env.cr.execute(f"SELECT {self._cols()} LIMIT {int(n)}")
