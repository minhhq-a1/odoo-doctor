from odoo import fields, models


class Ticket(models.Model):
    _name = "lc.ticket"
    _description = "Ticket"

    name = fields.Char()
    state = fields.Char()

    # Kept high: the loop cannot change what the call does, so it is plainly batchable.
    def _write_same_values(self):
        for ticket in self:
            ticket.write({"state": "done"})

    def _create_same_values(self, names):
        for _name in names:
            self.env["lc.ticket"].create({"state": "new"})

    def _query_the_loop_does_not_use(self):
        for ticket in self:
            tags = self.env["lc.ticket"].search([("state", "=", "new")])
            ticket.name = len(tags)

    # Demoted to medium: the shapes Odoo's own addons are written with.
    def _query_per_record(self):
        for ticket in self:
            self.env["lc.ticket"].search([("name", "=", ticket.name)])

    def _write_per_record_values(self):
        for ticket in self:
            ticket.write({"name": ticket.name.upper()})

    def _create_per_name(self, names):
        for name in names:
            self.env["lc.ticket"].create({"name": name})

    def _guarded_write(self):
        for ticket in self:
            if ticket.state == "draft":
                ticket.write({"state": "done"})

    def _write_among_other_work(self):
        for ticket in self:
            ticket.write({"state": "done"})
            ticket.message_post(body="done")

    def _query_after_a_write(self):
        for ticket in self:
            ticket.write({"state": "done"})
            self.env["lc.ticket"].search([("state", "=", "done")])

    def _query_in_a_while(self, names):
        while names:
            self.env["lc.ticket"].search([("state", "=", "new")])
            names.pop()
