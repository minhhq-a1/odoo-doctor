import ssl

import requests
from odoo import api, models


class BrSync(models.Model):
    _name = "br.sync"
    _description = "Backlog rules sample"

    # --- deprecated-orm-api-usage -------------------------------------------------
    def read_group(self, domain, fields, groupby, **kw):  # true positive: dead override
        return super().read_group(domain, fields, groupby, **kw)  # not reported twice

    def stats(self):
        self.env["br.sync"].read_group([], ["id:count"], ["create_uid"])  # true positive
        self.env["br.sync"]._read_group([], ["create_uid"], ["id:count"])  # fine
        return self.check_access("read")  # fine

    def toggle_active(self):  # an override is not reported, only calls are
        return super().toggle_active()

    # --- tls-verification-disabled / http-request-without-timeout -----------------
    def fetch(self, url):
        requests.get(url, verify=False, timeout=5)  # tls: true positive
        requests.get(url, timeout=5)  # fine
        requests.post(url, json={})  # timeout: true positive
        return requests.get(url, **self._options())  # options may carry the timeout

    def context(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False  # tls: true positive
        return ctx

    # --- manual-cr-commit ---------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        self.env.cr.commit()  # true positive: splits the write
        return res

    def action_batch(self):
        self.env.cr.commit()  # medium: ordinary method, no score effect

    def _cron_batch(self):
        self.env.cr.commit()  # cron: fine

    def sync(self, auto_commit=False):
        if auto_commit:
            self.env.cr.commit()  # caller opted in: fine

    def isolated(self):
        with self.pool.cursor() as cr:
            cr.commit()  # a cursor of its own: fine

    def marked(self):
        self.env.cr.commit()  # pylint: disable=invalid-commit

    @api.model
    def _options(self):
        return {"timeout": 3}
