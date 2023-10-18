# -*- coding: utf-8 -*-

from odoo import models, fields, api

class SignItemType(models.Model):
    _inherit = 'sign.item.type'

    # Define las opciones de selección del tipo de elemento de firma
    item_type = fields.Selection([
        ('signature', "Signature"),
        ('initial', "Initial"),
        ('text', "Text"),
        ('textarea', "Multiline Text"),
        ('checkbox', "Checkbox"),
        ('selection', "Selection"),
        ('sequential', "Sequential"),
    ], required=True, string='Type', default='text')

    sequence_id = fields.Many2one('ir.sequence', string='Related Sequence')
    sequence_code = fields.Char(string='Sequence Code')
    sequence_prefix = fields.Char(string='Sequence Prefix')
    sequence_suffix = fields.Char(string='Sequence Suffix')
    sequence_padding = fields.Integer(string='Sequence Size')
    sequence_number_increment = fields.Integer(string='Step')
    sequence_next_number = fields.Integer(string='Next Number')

    @api.onchange('sequence_id')
    def _onchange_sequence_id(self):
        if self.sequence_id:
            # Actualiza los campos de la secuencia con los valores del modelo
            self.sequence_code = self.sequence_id.code
            self.sequence_prefix = self.sequence_id.prefix
            self.sequence_suffix = self.sequence_id.suffix
            self.sequence_padding = self.sequence_id.padding
            self.sequence_number_increment = self.sequence_id.number_increment
            self.sequence_next_number = self.sequence_id.number_next_actual

    def save_sequence_changes(self):
        for record in self:
            if record.sequence_id:
                # Actualiza los campos de la secuencia con los valores del modelo
                record.sequence_id.write({
                    'code': record.sequence_code,
                    'prefix': record.sequence_prefix,
                    'suffix': record.sequence_suffix,
                    'padding': record.sequence_padding,
                    'number_increment': record.sequence_number_increment,
                    'number_next_actual': record.sequence_next_number,
                })
