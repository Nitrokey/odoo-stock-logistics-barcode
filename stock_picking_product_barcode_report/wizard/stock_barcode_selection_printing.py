# Copyright 2020 Carlos Roca <carlos.roca@tecnativa.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from math import ceil, floor

from odoo import api, fields, models
from odoo.fields import Command

from .ean_barcode import (
    CODE128_QUIET,
    EAN_QUIET,
    code128_modules,
    ean_modules,
    modules_svg_src,
)

# Smallest font size of the label texts
LABEL_MIN_FONT_MM = 1.5
# Smallest height of the bars when long texts need more room
LABEL_MIN_BARS_MM = 4


class ProductPrintingQty(models.TransientModel):
    _name = "stock.picking.line.print"
    _rec_name = "product_id"
    _description = "Print Picking Line"

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain="[('id', '=', product_id)]",
    )
    quantity = fields.Float(digits="Product Unit of Measure", required=True)
    label_qty = fields.Integer(
        "Quantity of Labels", compute="_compute_label_qty", store=True, readonly=False
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
    )
    lot_id = fields.Many2one("stock.lot", string="Lot/Serial Number")
    result_package_id = fields.Many2one(
        comodel_name="stock.quant.package", string="Dest. package"
    )

    wizard_id = fields.Many2one("stock.picking.print", string="Wizard")
    move_line_id = fields.Many2one("stock.move.line", "Move", readonly=True)
    product_packaging_id = fields.Many2one(
        comodel_name="product.packaging",
        string="Packaging",
        domain="[('product_id', '=', product_id)]",
        groups="product.group_stock_packaging",
        check_company=True,
    )
    company_id = fields.Many2one(related="wizard_id.company_id")

    @api.depends("product_packaging_id", "quantity")
    def _compute_label_qty(self):
        self.label_qty = 1
        for line in self.filtered("product_packaging_id.print_one_label_by_item"):
            factor = line.product_packaging_id.qty
            line.label_qty = ceil(line.quantity / (factor or 1.0))

    def _get_label_layout(self):
        """Sizes in CSS px for the barcode label, derived from its paper format.
        Odoo renders with ``--zoom 96/dpi``, so one CSS px is one printer dot.
        Font sizes are estimates and maximums, the report fits the texts to
        ``text_width`` and ``height``.
        """
        self.ensure_one()
        paper = (
            self.env["ir.actions.report"]
            ._get_report("stock_picking_product_barcode_report.label_barcode_report")
            .get_paperformat()
        )
        dots_per_mm = (paper.dpi or 96) / 25.4
        width = floor(
            ((paper.print_page_width or 47) - paper.margin_left - paper.margin_right)
            * dots_per_mm
        )
        height = floor(
            ((paper.print_page_height or 29) - paper.margin_top - paper.margin_bottom)
            * dots_per_mm
        )
        code = self.product_id.barcode or ""
        bars_src = False
        bars_width = text_width = width
        if self.wizard_id.barcode_format != "gs1_128":
            bits = ean_modules(code)
            quiet = EAN_QUIET.get(len(code))
            if not bits:
                bits = code128_modules(code)
                quiet = CODE128_QUIET
            if bits:
                bars_src = modules_svg_src(bits)
                bars_width = len(bits) * max(1, floor(width / (len(bits) + quiet)))
                if quiet != CODE128_QUIET:
                    text_width = bars_width

        min_size = round(LABEL_MIN_FONT_MM * dots_per_mm)

        def fit(length, max_size, char_width=0.6):
            if length:
                max_size = min(max_size, text_width / (length * char_width))
            return max(min_size, floor(max_size))

        product = self.product_id
        if product.default_code and product.default_code == code:
            product = product.with_context(display_default_code=False)
        name = product.display_name or ""
        lot_name = self.lot_id.name or ""
        digits_max = max(min_size, floor(height * 0.2))
        name_max = max(min_size, floor(height * 0.21))
        lot_max = max(min_size, floor(height * 0.16))
        return {
            "height": height,
            "min_size": min_size,
            "bars_src": bars_src,
            "bars_width": bars_width,
            "bars_height": round(height * (0.37 if lot_name else 0.47)),
            "bars_min": round(LABEL_MIN_BARS_MM * dots_per_mm),
            "text_width": text_width,
            "name": name,
            "digits_max": digits_max,
            "digits_size": fit(len(code), digits_max),
            "name_max": name_max,
            "name_size": fit(len(name), name_max),
            "lot_max": lot_max,
            "lot_size": fit(len(lot_name) + 5, lot_max),
        }


class WizStockBarcodeSelectionPrinting(models.TransientModel):
    _name = "stock.picking.print"
    _description = "Wizard to select how many barcodes have to be printed"

    @api.model
    def _get_lang(self):
        return self.env["res.lang"].get_installed()

    @api.model
    def default_get(self, fields):
        ctx = self.env.context.copy()
        res = super().default_get(fields)
        if ctx.get("active_ids") and ctx.get("active_model") == "stock.picking":
            picking_ids = self.env["stock.picking"].browse(ctx.get("active_ids"))
            res.update({"picking_ids": [Command.link(p.id) for p in picking_ids]})
        if ctx.get("active_ids") and ctx.get("active_model") == "stock.move.line":
            stock_move_lines = self.env["stock.move.line"].browse(ctx.get("active_ids"))
            res.update({"stock_move_line_ids": stock_move_lines.ids})
        if ctx.get("active_ids") and ctx.get("active_model") == "stock.quant":
            lines = self._get_lines_from_quants()
            res.update({"product_print_moves": lines})
        if ctx.get("active_ids") and ctx.get("active_model") == "stock.lot":
            lines = self._get_lines_from_lots()
            res.update({"product_print_moves": lines})
        if ctx.get("barcode_label_product_ids"):
            lines = self._get_lines_from_products()
            res.update({"product_print_moves": lines})
        return res

    def _default_barcode_report(self):
        barcode_report = self.env.company.barcode_default_report
        if not barcode_report:
            barcode_report = self.env.ref(
                "stock_picking_product_barcode_report.action_label_barcode_report"
            )
        return barcode_report

    picking_ids = fields.Many2many("stock.picking")
    product_print_moves = fields.One2many(
        "stock.picking.line.print", "wizard_id", "Moves"
    )
    barcode_format = fields.Selection(
        selection=[("gs1_128", "Display GS1_128 format for barcodes")],
        default=lambda self: self.env.company.barcode_report_default_format,
    )
    barcode_report = fields.Many2one(
        comodel_name="ir.actions.report",
        string="Report to print",
        domain=[("is_barcode_label", "=", True)],
        default=_default_barcode_report,
        required=True,
    )
    is_custom_label = fields.Boolean(compute="_compute_is_custom_label")
    html_content = fields.Html()
    label_qty = fields.Integer(default=1)
    stock_move_line_ids = fields.Many2many("stock.move.line")
    lang = fields.Selection(comodel_name="res.lang", selection=_get_lang)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    @api.onchange("picking_ids", "stock_move_line_ids", "barcode_report")
    def _onchange_picking_ids(self):
        product_print_moves = [(Command.clear())]
        line_fields = [f for f in self.env["stock.picking.line.print"]._fields.keys()]
        product_print_moves_data_tmpl = self.env[
            "stock.picking.line.print"
        ].default_get(line_fields)
        stock_move_lines = self.stock_move_line_ids or self._get_move_lines(
            self.picking_ids
        )
        for move_line in stock_move_lines:
            product_print_moves_data = dict(product_print_moves_data_tmpl)
            product_print_moves_data.update(
                self._prepare_data_from_move_line(move_line)
            )
            if product_print_moves_data:
                product_print_moves.append(Command.create(product_print_moves_data))
        if self.stock_move_line_ids or self.picking_ids:
            self.product_print_moves = product_print_moves

    def _get_lines_from_quants(self):
        lines = []
        quants = self.env["stock.quant"].browse(self.env.context["active_ids"])
        for quant in quants:
            lines.append(
                Command.create(
                    {
                        "product_id": quant.product_id.id,
                        "label_qty": 1,
                        "quantity": quant.quantity,
                        "uom_id": quant.product_uom_id.id,
                        "lot_id": quant.lot_id.id,
                        "result_package_id": quant.package_id.id,
                    },
                )
            )
        return lines

    def _get_lines_from_products(self):
        products = self.env["product.product"].browse(
            self.env.context["barcode_label_product_ids"]
        )
        return [
            Command.create(
                {
                    "product_id": product.id,
                    "label_qty": 1,
                    "quantity": 1,
                    "uom_id": product.uom_id.id,
                },
            )
            for product in products
        ]

    def _get_lines_from_lots(self):
        lines = []
        lots = self.env["stock.lot"].browse(self.env.context["active_ids"])
        for lot in lots:
            lines.append(
                Command.create(
                    {
                        "product_id": lot.product_id.id,
                        "label_qty": 1,
                        "quantity": lot.product_qty,
                        "uom_id": lot.product_uom_id.id,
                        "lot_id": lot.id,
                    },
                )
            )
        return lines

    @api.model
    def _get_move_lines(self, picking):
        stock_move_line_to_print_id = self.env.context.get(
            "stock_move_line_to_print", False
        )
        if stock_move_line_to_print_id:
            return self.env["stock.move.line"].browse(stock_move_line_to_print_id)

        if self.barcode_report == self.env.ref(
            "stock_picking_product_barcode_report.action_label_barcode_report_quant_package"
        ):
            return picking.move_line_ids.filtered("result_package_id")
        elif self.barcode_report == self.env.ref(
            "stock_picking_product_barcode_report.action_label_barcode_report"
        ):
            return picking.move_line_ids.filtered("product_id.barcode")
        return picking.move_line_ids

    @api.model
    def _prepare_data_from_move_line(self, move_line):
        qty = self.env.context.get("force_quantity_line", move_line.quantity)
        return {
            "product_id": move_line.product_id.id,
            "quantity": qty,
            "move_line_id": move_line.id,
            "uom_id": move_line.product_uom_id.id,
            "lot_id": move_line.lot_id.id,
            "result_package_id": move_line.result_package_id.id,
            "product_packaging_id": move_line.move_id.product_packaging_id.id,
        }

    def print_labels(self):
        if self.is_custom_label:
            return self.barcode_report.report_action(self)
        print_move = self.product_print_moves.filtered(lambda p: p.label_qty > 0)
        if print_move:
            return self.barcode_report.report_action(self.product_print_moves)

    @api.onchange("barcode_report")
    def _compute_is_custom_label(self):
        for record in self:
            record.is_custom_label = record.barcode_report.is_custom_label

    def create_label_print_wiz_from_move_line(self, report_id, stock_move_lines):
        """Helper method to create this wizard from other models to print labels"""
        if isinstance(stock_move_lines, (int | list)):
            stock_move_lines = self.env["stock.move.line"].browse(stock_move_lines)
        wiz = self.env["stock.picking.print"].create(
            {
                "barcode_report": report_id,
                "product_print_moves": [
                    Command.create(
                        {
                            "product_id": sml.product_id.id,
                            "quantity": self.env.context.get(
                                "force_quantity_line", sml.quantity
                            ),
                            "move_line_id": sml.id,
                            "uom_id": sml.product_uom_id.id,
                            "lot_id": sml.lot_id.id,
                            "result_package_id": sml.result_package_id.id,
                            "product_packaging_id": self.env.context.get(
                                "packaging_id", False
                            ),
                        },
                    )
                    for sml in stock_move_lines
                ],
            }
        )
        return wiz
