from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SaleDiscountRule(models.Model):
    _name = "sale.discount.rule"
    _description = "Sale Discount Rule"
    _order = 'discount_percent desc'
    
    name = fields.Char('Rule Name', required=True)
    min_amount = fields.Float('Min Amount', required=True)
    max_amount = fields.Float('Max Amount', required=True)
    discount_percent = fields.Float('Discount %', required=True)
    customer_group = fields.Many2many('res.partner.category', string='customer Group')
    valid_from = fields.Date('Valid From', required=True)
    valid_to = fields.Date('Valid To', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', 'company', default=lambda self: self.env.company)

    @api.constrains('min_amount', 'max_amount', 'discount_percent')
    def _check_values(self):
        """ validate min amount and max amount also validate discount percent.
        """
        for rec in self:
            if rec.min_amount >= rec.max_amount:
                raise ValidationError(
                    'Min Amount must be less than Max Amount.'
                )
            if not (0 < rec.discount_percent <= 100):
                raise ValidationError(
                    'Discount must be between 0 and 100.'
                )

