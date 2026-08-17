from odoo import fields, models, api, _
from odoo.exceptions import UserError


class SupplierProductsWizard(models.TransientModel):
    _name = 'supplier.products.wizard'
    _description = 'Supplier Products Wizard'

    hotel_ids = fields.Many2many('pms.property', string='Hotels')
    hotel_id = fields.Many2one('pms.property', string='Hotel')
    seller_ids = fields.Many2many('res.partner', string='Seller', related='hotel_id.seller_ids')
    supplier_ids = fields.Many2many('res.partner', string='Suppliers', required=True, domain="[('id', 'not in', seller_ids)]")
    supplier_commercial_ids = fields.Many2many('res.partner', string='Commercial Supplier', relation="supplier_commercial_rel")
    product_supplier_ids = fields.Many2many(
        'product.product',
        string='Allowed products by seller',
        relation="wizard_pms_property_product_supplier_rel",
        column1="product_id",
        column2="property_id",
    )
    product_ids = fields.Many2many('product.product', string='Products', domain="[('id', 'in', product_supplier_ids)]")

    @api.onchange('supplier_ids', 'supplier_commercial_ids')
    def onchange_supplier_commercial_ids(self):
        for wizard in self:
            wizard.supplier_commercial_ids = wizard.supplier_ids.mapped('commercial_partner_id')
            suppliers = self.env['product.supplierinfo'].search([
                '|',
                ('partner_id', 'in', wizard.supplier_ids.ids),
                ('partner_id', 'in', wizard.supplier_commercial_ids.ids)
            ])

            if suppliers:
                supplier_products = suppliers.mapped('product_tmpl_id.product_variant_ids')
                supplier_products += suppliers.mapped('product_id')
                wizard.product_ids = [(6, 0, supplier_products.ids)]
                wizard.product_supplier_ids = [(6, 0, supplier_products.ids)]
            else:
                wizard.product_ids = [(5,)]
                wizard.product_supplier_ids = [(5,)]

    def action_confirm(self):
        for wizard in self:
            if wizard.hotel_ids:
                for hotel in wizard.hotel_ids:
                    hotel.product_ids += wizard.product_ids
                    hotel.seller_ids += wizard.supplier_ids
                    hotel.onchange_seller_ids()
            elif wizard.hotel_id:
                wizard.hotel_id.product_ids += wizard.product_ids
                wizard.hotel_id.seller_ids += wizard.supplier_ids
                wizard.hotel_id.onchange_seller_ids()
            else:
                raise UserError(_("Please select at least one hotel."))

        return {'type': 'ir.actions.act_window_close'}
