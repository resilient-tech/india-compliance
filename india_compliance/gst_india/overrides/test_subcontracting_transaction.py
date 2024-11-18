import re

import frappe
from frappe.tests import IntegrationTestCase, change_settings
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
    po_dict = {
        "doctype": "Purchase Order",
        "supplier": args.get("supplier") or "_Test Registered Supplier",
        "is_subcontracted": 1,
        "items": args.get("items"),
        "supplier_warehouse": "Finished Goods - _TIRC",
        "do_not_save": 1,
        "do_not_submit": 1,
    }

    po = create_transaction(**po_dict)

    if po.is_subcontracted:
        supp_items = po.get("supplied_items")
        for d in supp_items:
            if not d.reserve_warehouse:
                d.reserve_warehouse = "Stores - _TIRC"

    return po.submit()


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
            "bill_from_address": "_Test Indian Registered Company-Billing",
            "bill_to_address": "_Test Registered Supplier-Billing",
        }
    )

    doc = frappe.get_doc(ste_dict)
    doc.insert()

    return doc.submit()


class TestSubcontractingTransaction(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        make_raw_materials()
        make_service_items()
        make_subcontracted_items()
        make_boms()

    def _create_stock_entry(self, doc_args):
        """Generate Stock Entry to test e-Waybill functionalities"""
        doc_args.update({"doctype": "Stock Entry"})

        stock_entry = create_transaction(**doc_args)
        return stock_entry

    def test_create_and_update_stock_entry(self):
        # Create a subcontracting transaction
        args = {
            "stock_entry_type": "Send to Subcontractor",
            "purpose": "Send to Subcontractor",
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
                    "taxable_value": 100,
                }
            ],
            "company": "_Test Indian Registered Company",
            "base_grand_total": 100,
        }

        stock_entry = self._create_stock_entry(args)

        # Update the subcontracting transaction
        stock_entry.run_method("onload")  # update virtual fields
        stock_entry.select_print_heading = "Credit Note"
        stock_entry.save()

        self.assertEqual(stock_entry.select_print_heading, "Credit Note")

    def test_validation_for_doc_references(self):
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

        po = create_purchase_order(items=service_item)
        sco = create_subcontracting_order(po_name=po.name)

        rm_items = get_rm_items(sco.supplied_items)
        se = make_stock_transfer_entry(sco_no=sco.name, rm_items=rm_items)

        return_se = get_materials_from_supplier(
            sco.name, [d.name for d in sco.supplied_items]
        )
        return_se.save()

        scr = make_subcontracting_receipt(sco.name)
        scr.submit()

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Please Select Original Document Reference*)"),
            return_se.submit,
        )

        return_se.reload()
        return_se.append(
            "doc_references",
            {"link_doctype": "Stock Entry", "link_name": se.name},
        )
        return_se.submit()

    @change_settings(
        "GST Settings",
        {"enable_api": 1, "enable_e_waybill": 1, "enable_e_waybill_for_sc": 1},
    )
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
            items=service_item, supplier="_Test Unregistered Supplier"
        )

        create_subcontracting_order(po_name=po.name)
