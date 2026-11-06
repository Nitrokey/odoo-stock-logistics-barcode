# Copyright 2026 Nitrokey GmbH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_open_barcode_label_wizard(self):
        return self.product_variant_ids.action_open_barcode_label_wizard()


class ProductProduct(models.Model):
    _inherit = "product.product"

    def action_open_barcode_label_wizard(self):
        products = self.filtered("barcode")
        if not products:
            raise UserError(_("This product has no barcode."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Print barcode labels"),
            "res_model": "stock.picking.print",
            "view_mode": "form",
            "target": "new",
            "context": {"barcode_label_product_ids": products.ids},
        }
