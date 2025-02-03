import re

import frappe
from frappe.tests import IntegrationTestCase
from erpnext.controllers.subcontracting_controller import (
    get_materials_from_supplier,
    make_rm_stock_entry,
)
from erpnext.controllers.tests.test_subcontracting_controller import get_rm_items
from erpnext.manufacturing.doctype.production_plan.test_production_plan import make_bom
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
    make_subcontracting_receipt,
)
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
        for item_default in [
            doc for doc in item.get("item_defaults") if not doc.default_warehouse
        ]:
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
            "bill_from_address": args.bill_from_address
            or "_Test Indian Registered Company-Billing",
            "bill_to_address": args.bill_to_address
            or "_Test Registered Supplier-Billing",
        }
    )

    doc = frappe.get_doc(ste_dict)
    doc.insert()

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


SERVICE_ITEM = {
    "item_code": "Subcontracted Service Item 1",
    "qty": 10,
    "rate": 100,
    "fg_item": "Subcontracted Item SA1",
    "fg_item_qty": 10,
}


class TestSubcontractingTransaction(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        make_raw_materials()
        make_service_items()
        make_subcontracted_items()
        make_boms()

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
        self.assertEqual(sco.total_taxes, None)

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

        self.assertEqual(se.total_taxes, None)

    def test_subcontracting_validations(self):
        po = create_purchase_order(
            **SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC"
        )
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

        po = create_purchase_order(
            **SERVICE_ITEM, supplier_warehouse="Finished Goods - _TIRC"
        )
        sco = create_subcontracting_order(po_name=po.name)

        rm_items = get_rm_items(sco.supplied_items)
        se = make_stock_transfer_entry(sco_no=sco.name, rm_items=rm_items)

        return_se = get_materials_from_supplier(
            sco.name, [d.name for d in sco.supplied_items]
        )
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
        doc_references_data = get_stock_entry_references(
            filters=filters, only_linked_references=True
        )
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
