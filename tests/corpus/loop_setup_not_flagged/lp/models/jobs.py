from odoo import api, fields, models
from odoo.tools import split_every


class Job(models.Model):
    _name = 'lp.job'
    _description = 'Job'

    name = fields.Char()

    @api.autovacuum
    def _gc(self):
        # the loop's own iterable runs once: no finding
        for channel in self.env['lp.job'].search([]):
            # paged delete: the search is the batching, not the problem
            while True:
                jobs = self.search([('name', '=', channel.name)], limit=1000)
                if not jobs:
                    break
                jobs.unlink()

    def _by_chunk(self, ids):
        for chunk in split_every(100, ids):
            self.search([('id', 'in', chunk)])

    def _per_record(self):
        for rec in self:
            # one query per record: the real finding of this case
            self.env['lp.job'].search([('name', '=', rec.name)])
