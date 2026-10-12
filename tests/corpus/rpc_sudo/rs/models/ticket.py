from odoo import fields, models


class Ticket(models.Model):
    _name = "rs.ticket"
    _description = "Ticket"

    name = fields.Char()
    user_id = fields.Many2one("res.users")

    def close(self, ticket_id):
        # a caller-chosen id is elevated and changed with no check: high
        self.env["rs.ticket"].sudo().browse(ticket_id).write({"name": "closed"})

    def peek(self, ticket_id):
        # elevated read of a caller-chosen id: review (medium)
        return self.env["rs.ticket"].sudo().browse(ticket_id).name

    def close_checked(self, ticket_id):
        ticket = self.env["rs.ticket"].browse(ticket_id)
        ticket.check_access("write")
        ticket.sudo().write({"name": "closed"})

    def close_filtered(self, ids):
        # search runs with the caller's rights: already limited to what they see
        tickets = self.search([("id", "in", ids)])
        tickets.sudo().write({"name": "closed"})

    def mine(self, ticket_id):
        return self.sudo().search(
            [("id", "=", ticket_id), ("user_id", "=", self.env.user.id)]
        )

    def _internal(self, ticket_id):
        return self.env["rs.ticket"].sudo().browse(ticket_id).unlink()
