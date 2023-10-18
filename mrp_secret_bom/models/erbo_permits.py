from odoo import fields, models


class ErboPermits(models.Model):
    _inherit = "mrp.bom"

    recipe_type = fields.Selection(
        [("normal", "Normal"), ("concentrated", "Concentrated"), ("premix", "Premix")],
        string="Type of Recipe",
        default="normal",
    )
