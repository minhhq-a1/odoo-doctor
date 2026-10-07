from odoo import models


class Tools(models.AbstractModel):
    _name = 'pr.tools'
    _description = 'Tools'

    def purge(self, attachments):
        # the table of a model is a trusted identifier
        self.env.cr.execute(f"DELETE FROM {attachments._table} WHERE id IN %s", [(1,)])

    def unsafe(self, table):
        self.env.cr.execute(f"DELETE FROM {table} WHERE id = 1")
