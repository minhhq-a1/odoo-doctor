from odoo import fields, models


class Note(models.Model):
    _name = "sc.note"
    _description = "Note"

    name = fields.Char()

    def allocate(self):
        # We do sudo because the user who finishes the work may not have
        # access to the notes of other teams.
        total = len(self)
        label = "x"
        for other in self.env["sc.note"].sudo().search([]):
            other.name = f"{label}{total}"

    def documented(self):
        """Notes of this team, read as sudo: operators cannot see other teams' rules."""
        self.ensure_one()
        return self.sudo().name

    def checked_first(self):
        self.env["sc.note"].browse(self.ids).check_access("read")  # before sudo(): own rights
        return self.sudo().name

    def already_elevated(self):
        self = self.sudo()
        first = self.env["sc.note"].sudo().search([], limit=1)
        return first | self.sudo().browse(self.ids)

    def bare(self):
        return self.sudo().name

    def unrelated_comment_above(self):
        total = len(self)  # count them
        return self.sudo().name + str(total)

    def far_away_note(self):
        # sudo is needed here because of the portal.
        a = 1
        b = 2
        c = 3
        d = 4
        e = 5
        f = 6
        return self.sudo().name, a + b + c + d + e + f

    def other_environment(self):
        self = self.sudo()
        return self.env["res.partner"].with_user(2).sudo().search([])
