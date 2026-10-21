from odoo import fields, models


class Wizard(models.TransientModel):
    _name = "prov.wizard"
    _description = "A field of a wizard is typed in by the user"

    name = fields.Char()

    def action_field(self):
        self.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{self.name}'")

    def action_mapped(self):
        names = ",".join(self.mapped("name"))
        self.env.cr.execute(f"SELECT id FROM res_partner WHERE name IN ({names})")

    def action_loop(self):
        for rec in self:
            self.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{rec.name}'")

    def action_metadata(self):
        self.env.cr.execute(f"SELECT id FROM {self._table} WHERE id = {self.id}")

    def action_ids_and_fields(self):
        self.env.cr.execute(f"SELECT id FROM res_partner WHERE id IN {self.ids}")
        self.env.cr.execute(f"SELECT {self._fields['name'].name} FROM res_partner")
