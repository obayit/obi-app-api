from odoo import models, http
from odoo.http import request
import odoo.models as odoo_models
from odoo.osv import expression


class ProductTemplate(models.Model):
    _inherit = "product.template"
    # expose private functions to mobile app

    def obi_app_get_first_possible_combination(self, *args, **kwargs):
        return self._get_first_possible_combination(*args, **kwargs).ids


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    def obi_app_get_extra_price(self, combination_params):
        product_template_id = combination_params['product_template_id']
        product_id = combination_params['product_id']
        combination = combination_params['combination']
        add_qty = combination_params['add_qty']
        parent_combination = combination_params.get('parent_combination')

        product_template = self.env['product.template'].browse(product_template_id and int(product_template_id))

        combination_info = product_template._get_combination_info(
            combination=self.env['product.template.attribute.value'].browse(combination),
            product_id=product_id and int(product_id),
            add_qty=add_qty and float(add_qty) or 1.0,
            parent_combination=self.env['product.template.attribute.value'].browse(parent_combination),
        )
        return [
            {"id": r.id, "extra_price": extra}
            for r in self
            # walrus operator := introduced in python 3.8
            if (extra := r._get_extra_price(combination_info)) != 0
        ]

