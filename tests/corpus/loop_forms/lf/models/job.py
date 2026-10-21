from odoo import fields, models


class Job(models.Model):
    _name = "lf.job"
    _description = "Job"

    name = fields.Char()

    def _comprehension(self):
        # one query per record, written as a comprehension
        return [self.env["lf.job"].search([("name", "=", r.name)]) for r in self]

    def _search_read(self):
        for rec in self:
            self.env["lf.job"].search_read([("name", "=", rec.name)], ["name"])

    def _local_recordset(self):
        jobs = self.env["lf.job"].search([])
        for job in jobs:
            job.write({"name": "x"})

    def _first_iterable_runs_once(self):
        return [j.name for j in self.env["lf.job"].search([])]

    def _bounded(self):
        return [self.env[m].search_count([]) for m in ("res.partner", "res.users")]

    def _read_groups_are_data(self):
        groups = self.env["lf.job"].read_group([], ["name"], ["name"])
        for group in groups:
            group.get("name")


class Gateway:
    """Not a model: self.client is an HTTP client, not a recordset."""

    def __init__(self, client):
        self.client = client

    def push(self, names):
        for name in names:
            self.client.search(name)
            self.client.create(name)
            self.client.write(name)
