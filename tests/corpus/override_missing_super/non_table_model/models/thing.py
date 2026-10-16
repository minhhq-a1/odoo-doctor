from odoo import api, models


class Board(models.AbstractModel):
    _name = "x.board"
    _description = "Board"
    _auto = False

    @api.model_create_multi
    def create(self, vals_list):
        return self

    def copy(self, default=None):
        return self.browse()
