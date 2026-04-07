import re
import unittest.mock as mock

import frappe
from erpnext.controllers.subcontracting_controller import (
    get_materials_from_supplier,
    make_rm_stock_entry,
)
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
    make_subcontracting_receipt,
)
from frappe.tests import IntegrationTestCase

with mock.patch("frappe.db"), mock.patch("frappe.new_doc"), mock.patch("frappe.get_doc"):
    from erpnext.controllers.tests.test_subcontracting_controller import get_rm_items
    from erpnext.manufacturing.doctype.production_plan.test_production_plan import (
        make_bom,
    )
    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
        make_stock_entry as make_se_from_pr,
    )
    from erpnext.stock.doctype.stock_entry.stock_entry import make_stock_in_entry
    from erpnext.subcontracting.doctype.subcontracting_order.test_subcontracting_order import (
        create_subcontracting_order,
    )

from india_compliance.gst_india.utils.tests import create_transaction


def make_raw_materials():
    raw_materials = {
        "Subcontracted SRM Item 1": {"valuation_rate": 20},
        "Subcontracted SRM Item 2": {"valuation_rate": 20},
    }

    for item, properties in raw_materials.items():
        if not frappe.db.exists("Item", item):
            properties.update({"is_stock_item": 1})
            make_item(item, properties)


def make_service_items():
    service_items = {
        "Subcontracted Service Item 1": {},
    }

    for item, properties in service_items.items():
        if not frappe.db.exists("Item", item):
            properties.update({"is_stock_item": 0})
            make_item(item, properties)


def make_subcontracted_items():
    sub_contracted_items = {
        "Subcontracted Item SA1": {},
        "Subcontracted Item SA2": {},
    }

    for item, properties in sub_contracted_items.items():
        if not frappe.db.exists("Item", item):
            properties.update({"is_stock_item": 1, "is_sub_contracted_item": 1})
            make_item(item, properties)


def make_boms():
    boms = {
        "Subcontracted Item SA1": [
            "Subcontracted SRM Item 1",
            "Subcontracted SRM Item 2",
        ],
        "Subcontracted Item SA2": [
            "Subcontracted SRM Item 1",
        ],
    }

    for item_code, raw_materials in boms.items():
        if not frappe.db.exists("BOM", {"item": item_code}):
            make_bom(
                item=item_code,
                raw_materials=raw_materials,
                rate=100,
                company="_Test Indian Registered Company",
            )


def make_item(item_code=None, properties=None):
    if not item_code:
        item_code = frappe.generate_hash(length=16)

    if frappe.db.exists("Item", item_code):
        return frappe.get_doc("Item", item_code)

    item = frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_code,
            "description": item_code,
            "item_group": "Products",
            "gst_hsn_code": "85011011",
        }
    )

    if properties:
        item.update(properties)

    if item.is_stock_item:
        for item_default in [doc for doc in item.get("item_defaults") if not doc.default_warehouse]:
            item_default.default_warehouse = "Stores - _TIRC"
            item_default.company = "_Test Indian Registered Company"

    return item.insert()


def create_purchase_order(**args):
    args.update(
        {
            "doctype": "Purchase Order",
            "is_subcontracted": 1,
        }
    )

    return create_transaction(**args)


def make_stock_transfer_entry(**args):
    args = frappe._dict(args)

    items = []
    for row in args.rm_items:
        row = frappe._dict(row)

        item = {
            "item_code": row.main_item_code or args.main_item_code,
            "rm_item_code": row.item_code,
            "qty": row.qty or 1,
            "item_name": row.item_code,
            "rate": row.rate or 100,
            "stock_uom": row.stock_uom or "Nos",
            "warehouse": row.warehouse,
        }

        items.append(item)

    ste_dict = make_rm_stock_entry(args.sco_no, items)
    ste_dict.update(
        {
            "bill_from_address": args.bill_from_address or "_Test Indian Registered Company-Billing",
            "bill_to_address": args.bill_to_address or "_Test Registered Supplier-Billing",
        }
    )

    doc = frappe.get_doc(ste_dict)
    doc.insert()

    if args.do_not_submit:
        return doc

    return doc.submit()


def make_stock_entry(**args):
    items = [
        {
            "item_code": "_Test Trading Goods 1",
            "qty": 1,
            "s_warehouse": args.get("from_warehouse") or "Stores - _TIRC",
            "t_warehouse": args.get("to_warehouse") or "Finished Goods - _TIRC",
            "amount": 100,
        }
    ]
    se = frappe.new_doc("Stock Entry")
    se.update(
        {
            "purpose": args.get("purpose") or "Material Receipt",
            "stock_entry_type": args.get("purpose") or "Material Receipt",
            "company": args.get("company") or "_Test Indian Registered Company",
            "items": args.get("items") or items,
        }
    )

    return se


def create_subcontracting_data():
    make_raw_materials()
    make_service_items()
    make_subcontracted_items()
    make_boms()


SERVICE_ITEM = {
    "item_code": "Subcontracted Service Item 1",
    "qty": 10,
    "rate": 100,
    "fg_item": "Subcontracted Item SA1",
    "fg_item_qty": 10,
}


class TestSubcontractingTransaction(IntegrationTestCase):
    ITEM_WITH_TAX = "Subcontracted SRM Item 1"
    ITEM_WITHOUT_TAX = "Subcontracted SRM Item 2"
    SCO_FG_ITEM = "Subcontracted Item SA1"
    TAX_TEMPLATE = "GST 18% - _TIRC"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_subcontracting_data()

        # Raw material
        item = frappe.get_doc("Item", cls.ITEM_WITH_TAX)
        if not any(d.item_tax_template == cls.TAX_TEMPLATE for d in item.taxes):
            item.append("taxes", {"item_tax_template": cls.TAX_TEMPLATE, "tax_category": ""})
            item.save()

        # Finished good
        fg_item = frappe.get_doc("Item", cls.SCO_FG_ITEM)
        if not any(d.item_tax_template == cls.TAX_TEMPLATE for d in fg_item.taxes):
            fg_item.append("taxes", {"item_tax_template": cls.TAX_TEMPLATE, "tax_category": ""})
            fg_item.save()

        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_waybill": 1,
                "enable_e_waybill_for_sc": 1,
            },
        )

    def _create_stock_entry(self, doc_args):
        """Generate Stock Entry to test e-Waybill functionalities"""
        doc_args.update({"doctype": "Stock Entry"})

        stock_entry = create_transaction(**doc_args)
        return stock_entry

    def _make_sco(self):
        po = create_purchase_order(**SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC")
        return create_subcontracting_order(po_name=po.name)

    def _rm_items(self, sco):
        return [
            {
                "main_item_code": row.main_item_code,
                "rm_item_code": row.rm_item_code,
                "qty": row.required_qty,
                "rate": row.rate,
                "stock_uom": row.stock_uom,
                "warehouse": row.reserve_warehouse,
            }
            for row in sco.supplied_items
        ]

    def test_create_and_update_stock_entry(self):
        # Create a subcontracting transaction
        args = {
            "stock_entry_type": "Send to Subcontractor",
            "bill_from_address": "_Test Indian Registered Company-Billing",
            "bill_to_address": "_Test Registered Supplier-Billing",
            "items": [
                {
                    "item_code": "_Test Trading Goods 1",
                    "qty": 1,
                    "gst_hsn_code": "61149090",
                    "s_warehouse": "Finished Goods - _TIRC",
                    "t_warehouse": "Goods In Transit - _TIRC",
                    "amount": 100,
                }
            ],
            "company": "_Test Indian Registered Company",
        }

        stock_entry = self._create_stock_entry(args)

        # Update the subcontracting transaction
        stock_entry.run_method("onload")  # update virtual fields
        stock_entry.select_print_heading = "Credit Note"
        stock_entry.save()

        self.assertEqual(stock_entry.select_print_heading, "Credit Note")

    def test_for_unregistered_company(self):
        po = create_purchase_order(
            company="_Test Indian Unregistered Company",
            supplier_warehouse="Finished Goods - _TIUC",
            **SERVICE_ITEM,
        )

        sco = create_subcontracting_order(po_name=po.name)
        self.assertEqual(sco.total_taxes, 0.0)

        rm_items = get_rm_items(sco.supplied_items)
        args = {
            "sco_no": sco.name,
            "rm_items": rm_items,
            "bill_from_address": "_Test Indian Unregistered Company-Billing",
            "bill_to_address": "_Test Unregistered Supplier-Billing",
        }
        se = make_stock_transfer_entry(**args)
        self.assertEqual(se.total_taxes, 0.0)

        scr = make_subcontracting_receipt(sco.name)
        scr.submit()
        self.assertEqual(scr.total_taxes, 0.0)

    def test_stock_entry_for_material_receipt(self):
        se = make_stock_entry()
        se.save()

        self.assertEqual(se.total_taxes, 0.0)

    def test_subcontracting_validations(self):
        po = create_purchase_order(**SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC")
        sco = create_subcontracting_order(po_name=po.name)

        rm_items = get_rm_items(sco.supplied_items)
        make_stock_transfer_entry(sco_no=sco.name, rm_items=rm_items)

        scr = make_subcontracting_receipt(sco.name)
        scr.save()

        scr.billing_address = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"(to ensure Company GSTIN is fetched in the transaction.$)"),
            scr.save,
        )

        scr.reload()
        self.assertEqual(scr.total_taxes, 252.0)

    def test_standalone_stock_entry(self):
        purpose = "Send to Subcontractor"
        se = make_stock_entry(purpose=purpose)

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"(to ensure Company GSTIN is fetched in the transaction.$)"),
            se.save,
        )

        se.bill_from_address = "_Test Indian Registered Company-Billing"

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"(.*is a mandatory field for GST Transactions.*)"),
            se.save,
        )

        se.bill_to_address = "_Test Registered Supplier-Billing"

        se.save()

    def test_validation_for_doc_references(self):
        from india_compliance.gst_india.overrides.subcontracting_transaction import (
            get_stock_entry_references,
        )

        po = create_purchase_order(**SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC")
        sco = create_subcontracting_order(po_name=po.name)

        rm_items = get_rm_items(sco.supplied_items)
        se = make_stock_transfer_entry(sco_no=sco.name, rm_items=rm_items)

        return_se = get_materials_from_supplier(sco.name, [d.name for d in sco.supplied_items])
        return_se.save()

        scr = make_subcontracting_receipt(sco.name)
        scr.save()
        scr.submit()

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Please Select Original Document Reference*)"),
            return_se.submit,
        )

        return_se.reload()

        filters = {
            "supplier": return_se.supplier,
            "supplied_items": [d.item_code for d in return_se.items],
            "subcontracting_orders": [return_se.subcontracting_order],
        }
        doc_references_data = get_stock_entry_references(filters=filters, only_linked_references=True)
        doc_references = [row[0] for row in doc_references_data]

        self.assertTrue(se.name in doc_references)

        return_se.append(
            "doc_references",
            {"link_doctype": "Stock Entry", "link_name": se.name},
        )
        return_se.submit()

    def test_validation_when_gstin_field_empty(self):
        service_item = [
            {
                "warehouse": "Stores - _TIRC",
                "item_code": "Subcontracted Service Item 1",
                "qty": 10,
                "rate": 100,
                "fg_item": "Subcontracted Item SA1",
                "fg_item_qty": 10,
            }
        ]

        po = create_purchase_order(
            items=service_item,
            supplier="_Test Unregistered Supplier",
            supplier_warhouse="Finished Goods - _TIUC",
        )

        sco = create_subcontracting_order(po_name=po.name, do_not_save=True)
        sco.supplier_warehouse = "Finished Goods - _TIUC"
        sco.save()
        sco.submit()

    def test_item_tax_template_set_on_sco_items_from_po(self):
        po = create_purchase_order(**SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC")
        sco = create_subcontracting_order(po_name=po.name)

        item_templates = {item.item_code: item.item_tax_template for item in sco.items}
        self.assertEqual(item_templates.get(self.SCO_FG_ITEM), self.TAX_TEMPLATE)

    def test_item_tax_template_not_overwritten_on_sco_items(self):
        po = create_purchase_order(**SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC")
        sco = create_subcontracting_order(po_name=po.name, do_not_save=True)

        other_template = "GST 5% - _TIRC"
        for item in sco.items:
            if item.item_code == self.SCO_FG_ITEM:
                item.item_tax_template = other_template

        sco.save()

        templates = {item.item_code: item.item_tax_template for item in sco.items}
        self.assertEqual(templates.get(self.SCO_FG_ITEM), other_template)

    def test_item_tax_template_set_on_se_items_from_sco(self):
        sco = self._make_sco()
        se = make_rm_stock_entry(sco.name, self._rm_items(sco))

        items_by_code = {item.get("item_code"): item for item in se.get("items", [])}

        self.assertEqual(
            items_by_code[self.ITEM_WITH_TAX].get("item_tax_template"),
            self.TAX_TEMPLATE,
        )
        self.assertFalse(items_by_code[self.ITEM_WITHOUT_TAX].get("item_tax_template"))


class TestAddressMappingAfterMapping(IntegrationTestCase):
    """
    Verifies bill_from_address / bill_to_address and their GSTINs are mapped
    correctly in Stock Entries created via get_mapped_doc from each source doctype.

    Scenarios (mirrors _get_fields_mapping logic):
      1. Subcontracting Order  → SE "Send to Subcontractor"
      2. Subcontracting Order  → SE "Material Transfer" (return of inputs)
      3. Purchase Receipt      → SE "Material Transfer"
      4. Stock Entry           → SE "Material Transfer"
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.savepoint("before_test_address_mapping")
        create_subcontracting_data()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        frappe.db.rollback(save_point="before_test_address_mapping")

    def _make_sco(self):
        po = create_purchase_order(**SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC")
        return create_subcontracting_order(po_name=po.name)

    def test_sco_to_se_send_to_subcontractor(self):
        sco = self._make_sco()
        rm_items = get_rm_items(sco.supplied_items)

        se = make_rm_stock_entry(sco.name, rm_items)

        self.assertEqual(se.purpose, "Send to Subcontractor")
        self.assertEqual(se.bill_from_address, sco.billing_address)
        self.assertEqual(se.bill_from_gstin, sco.company_gstin)
        self.assertEqual(se.bill_to_address, sco.supplier_address)
        self.assertEqual(se.bill_to_gstin, sco.supplier_gstin)
        # SCO has no dispatch_address; after reverse: ship_from=shipping_address, ship_to=None
        self.assertEqual(se.ship_from_address, sco.shipping_address)
        self.assertIsNone(se.ship_to_address)

    def test_sco_to_se_material_transfer_return(self):
        sco = self._make_sco()
        rm_items = get_rm_items(sco.supplied_items)

        # Materials must reach the supplier warehouse before they can be returned.
        make_stock_transfer_entry(
            sco_no=sco.name,
            rm_items=rm_items,
            bill_from_address=sco.billing_address,
            bill_to_address=sco.supplier_address,
        )

        return_se = get_materials_from_supplier(sco.name, [d.name for d in sco.supplied_items])

        self.assertEqual(return_se.purpose, "Material Transfer")
        self.assertTrue(return_se.is_return)
        # Supplier becomes the sender; company becomes the receiver.
        self.assertEqual(return_se.bill_from_address, sco.supplier_address)
        self.assertEqual(return_se.bill_from_gstin, sco.supplier_gstin)
        self.assertEqual(return_se.bill_to_address, sco.billing_address)
        self.assertEqual(return_se.bill_to_gstin, sco.company_gstin)
        # SCO has no dispatch_address; ship_from stays empty, ship_to=shipping_address (not reversed)
        self.assertIsNone(return_se.ship_from_address)
        self.assertEqual(return_se.ship_to_address, sco.shipping_address)

    def test_pr_to_se_material_transfer(self):
        pr = create_transaction(doctype="Purchase Receipt")

        se = make_se_from_pr(pr.name)

        self.assertEqual(se.purpose, "Material Transfer")
        self.assertEqual(se.bill_from_address, pr.billing_address)
        self.assertEqual(se.bill_from_gstin, pr.company_gstin)
        self.assertEqual(se.bill_to_address, pr.supplier_address)
        self.assertEqual(se.bill_to_gstin, pr.supplier_gstin)
        self.assertEqual(se.ship_from_address, pr.shipping_address)
        self.assertEqual(se.ship_to_address, pr.dispatch_address)

    def test_se_to_se_material_transfer(self):
        # Add stock so the Material Transfer SE can be submitted.
        create_transaction(doctype="Purchase Receipt")

        source_se = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "stock_entry_type": "Material Transfer",
                "company": "_Test Indian Registered Company",
                "bill_from_address": "_Test Indian Registered Company-Billing",
                "bill_from_gstin": "24AAQCA8719H1ZC",
                "bill_to_address": "_Test Registered Supplier-Billing",
                "bill_to_gstin": "24AABCR6898M1ZN",
                "bill_to_gst_category": "Registered Regular",
                "items": [
                    {
                        "item_code": "_Test Trading Goods 1",
                        "qty": 1,
                        "gst_hsn_code": "61149090",
                        "s_warehouse": "Stores - _TIRC",
                        "t_warehouse": "Finished Goods - _TIRC",
                    }
                ],
            }
        )
        source_se.save()
        source_se.submit()

        target_se = make_stock_in_entry(source_se.name)

        self.assertEqual(target_se.purpose, "Material Transfer")
        self.assertEqual(target_se.bill_from_address, source_se.bill_from_address)
        self.assertEqual(target_se.bill_from_gstin, source_se.bill_from_gstin)
        self.assertEqual(target_se.bill_to_address, source_se.bill_to_address)
        self.assertEqual(target_se.bill_to_gstin, source_se.bill_to_gstin)
        self.assertEqual(target_se.ship_from_address, source_se.ship_from_address)
        self.assertEqual(target_se.ship_to_address, source_se.ship_to_address)
