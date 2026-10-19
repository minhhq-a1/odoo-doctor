from odoo import fields, models

MIXINS = ["mail.thread", "mail.activity.mixin"]


class BaseThing(models.Model):
    _name = "it.base"
    _description = "Base"

    name = fields.Char()
    code = fields.Char()


class BaseThingExtension(models.Model):
    # an extension written with a tuple: the field it adds must be known
    _inherit = ("it.base",)

    added = fields.Char()


class TupleMixins(models.Model):
    _name = "it.tup"
    _description = "Tuple"
    _inherit = ("mail.thread", "mail.activity.mixin")

    name = fields.Char()


class ListMixins(models.Model):
    _name = "it.lst"
    _description = "List"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char()


class Prototype(models.Model):
    # copies every field of it.base through a tuple
    _name = "it.proto"
    _description = "Prototype"
    _inherit = ("it.base",)

    extra = fields.Char()


class Computed(models.Model):
    # the parents are not written out: the model may have any field
    _name = "it.dyn"
    _description = "Dynamic"
    _inherit = MIXINS

    name = fields.Char()


class Unresolved(models.Model):
    _name = "it.unknown"
    _description = "Unresolved"
    _inherit = ("not.a.known.mixin",)

    name = fields.Char()
