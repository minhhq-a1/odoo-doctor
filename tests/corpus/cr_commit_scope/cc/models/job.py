from odoo import api, models


class Job(models.Model):
    _name = "cc.job"
    _description = "Job"

    def _own_cursor(self):
        # a cursor this code opened: committing it is its job
        with self.pool.cursor() as cr:
            cr.commit()
        env = api.Environment(self.pool.cursor(), 1, {})
        env.cr.commit()

    def _request_cursor(self, cr, env):
        # these are the request's, not the cursor opened in _own_cursor
        cr.commit()
        env.cr.commit()

    def write(self, vals):
        res = super().write(vals)
        self.env.cr.commit()
        return res
