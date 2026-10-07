from odoo import fields, models


class Order(models.Model):
    _name = 'np.order'
    _description = 'Order'

    partner_id = fields.Many2one('res.partner', ondelete='restrict')
    summary = fields.Char(compute='_compute_summary')

    def _compute_summary(self):
        # a loop over a recordset is prefetched: one query per field, not per record
        for order in self:
            order.summary = order.partner_id.country_id.name or ''

    def names_from_ids(self, partner_ids):
        names = []
        for partner_id in partner_ids:
            # a singleton browsed per iteration starts with an empty prefetch
            partner = self.env['res.partner'].browse(partner_id)
            names.append(partner.country_id.name)
        return names

    def names_prefetched(self, partner_ids):
        names = []
        for partner_id in partner_ids:
            partner = self.env['res.partner'].with_prefetch(partner_ids).browse(partner_id)
            names.append(partner.name)
        return names
