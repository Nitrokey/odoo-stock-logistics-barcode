# Copyright 2020 Carlos Roca <carlos.roca@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, call

from odoo import Command

from odoo.addons.base.tests.common import BaseCommon

from ..controllers.main import SVGWitoutTextWriter
from ..wizard.ean_barcode import ean_modules


class TestStockPickingProductBarcodeReport(BaseCommon):
    def setUp(self):
        super().setUp()
        self.supplier_location = self.env.ref("stock.stock_location_suppliers")
        self.stock_location = self.env.ref("stock.stock_location_stock")
        self.product_barcode = self.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "consu",
                "is_storable": True,
                "barcode": "1001",
            }
        )
        self.product_no_barcode = self.env["product.product"].create(
            {"name": "Test Product 2", "type": "consu", "is_storable": True}
        )
        self.package = self.env["stock.quant.package"].create({"name": "Pack-Test"})
        partner = self.env["res.partner"].create({"name": "Test Partner"})
        self.picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "partner_id": partner.id,
                "picking_type_id": self.env.ref(
                    "stock.picking_type_in"
                ).id,  # Operation type Receipts
                "move_ids_without_package": [
                    Command.create(
                        {
                            "name": "Test 01",
                            "product_id": self.product_barcode.id,
                            "product_uom_qty": 20,
                            "product_uom": self.product_barcode.uom_id.id,
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                        },
                    ),
                    Command.create(
                        {
                            "name": "Test 02",
                            "product_id": self.product_no_barcode.id,
                            "product_uom_qty": 10,
                            "product_uom": self.product_barcode.uom_id.id,
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                        },
                    ),
                ],
            }
        )
        self.picking.action_confirm()
        self.picking._action_done()
        for move_line_id in self.picking.move_line_ids:
            move_line_id.result_package_id = self.package
        self.wizard = (
            self.env["stock.picking.print"]
            .with_context(active_ids=self.picking.ids, active_model="stock.picking")
            .create({})
        )

    def test_wizard_creation(self):
        self.wizard.barcode_report = self.env.ref(
            "stock_picking_product_barcode_report.action_label_barcode_report"
        )
        self.wizard._onchange_picking_ids()
        self.assertEqual(1, len(self.wizard.product_print_moves.ids))
        line = self.wizard.product_print_moves[0]
        self.assertEqual(line.label_qty, 1)
        self.assertEqual(line.product_id.id, self.product_barcode.id)
        # This two sentences are added just for check that not throw an exception
        self.wizard.barcode_format = "gs1_128"
        self.wizard.print_labels()
        # Check that wizard add lines with packages and the label not
        # throw an exception when trying to print it
        self.wizard.barcode_report = self.env.ref(
            "stock_picking_product_barcode_report.action_label_barcode_report_quant_package"
        )
        self.wizard._onchange_picking_ids()
        self.assertEqual(2, len(self.wizard.product_print_moves.ids))
        line = self.wizard.product_print_moves[0]
        self.assertEqual(line.label_qty, 1)
        self.assertEqual(line.product_id.id, self.product_barcode.id)
        self.wizard.print_labels()

    def test_wizard_quants(self):
        quant = self.env["stock.quant"].create(
            {
                "product_id": self.product_barcode.id,
                "location_id": self.stock_location.id,
                "quantity": 20.0,
            }
        )
        quant_wizard = (
            self.env["stock.picking.print"]
            .with_context(**{"active_ids": quant.ids, "active_model": "stock.quant"})
            .create({})
        )
        quant_wizard.barcode_report = self.env.ref(
            "stock_picking_product_barcode_report.action_label_barcode_report"
        )
        self.assertEqual(len(quant_wizard.product_print_moves), 1)
        self.assertEqual(quant_wizard.product_print_moves.quantity, 20)
        quant_wizard.print_labels()

    def test_init(self):
        writer = SVGWitoutTextWriter(module_max_height=200)
        self.assertEqual(writer.module_max_height, 200)
        writer = SVGWitoutTextWriter()
        self.assertEqual(writer.module_max_height, 100)

    def test_create_module(self):
        writer = SVGWitoutTextWriter(module_max_height=100)
        writer._document = MagicMock()
        writer._group = MagicMock()
        xpos = 10
        ypos = 20
        width = 30
        color = "black"
        writer._create_module(xpos, ypos, width, color)
        writer._document.createElement.assert_called_once_with("rect")
        element = writer._document.createElement.return_value
        element.setAttribute.assert_has_calls(
            [
                call("x", "10.000mm"),
                call("y", "20.000mm"),
                call("width", "30.000mm"),
                call("height", "100"),
                call("style", "fill:black"),
            ],
            any_order=False,
        )
        writer._group.appendChild.assert_called_once_with(element)

    def test_ean_modules(self):
        self.assertEqual(
            ean_modules("5901234123457"),
            "10100010110100111011001100100110111101001110101010110011011011"
            "001000010101110010011101000100101",
        )
        self.assertEqual(len(ean_modules("96385074")), 67)
        self.assertFalse(ean_modules("5901234123458"))
        self.assertFalse(ean_modules("1001"))

    def test_label_layout(self):
        self.product_barcode.barcode = "5901234123457"
        paper = self.env.ref("stock_picking_product_barcode_report.paperformat_label")
        paper.write({"page_width": 30, "page_height": 15, "margin_top": 0, "dpi": 203})
        line = self.env["stock.picking.line.print"].create(
            {"product_id": self.product_barcode.id, "quantity": 1}
        )
        layout = line._get_label_layout()
        self.assertTrue(layout["bars_src"])
        # 2 printer dots per module
        self.assertEqual(layout["text_width"], 95 * 2)
        html = (
            self.env["ir.actions.report"]
            ._render_qweb_html(
                "stock_picking_product_barcode_report.label_barcode_report", line.ids
            )[0]
            .decode()
        )
        self.assertIn("data:image/svg+xml;base64,", html)
        self.assertEqual(html.count("5901234123457"), 1)
