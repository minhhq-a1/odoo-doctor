from odoo import models


class Util(models.AbstractModel):
    _name = "mc.util"
    _description = "Util"

    def company(self):
        return self.env.ref("base.main_company")

    def current(self):
        return self.env.company
