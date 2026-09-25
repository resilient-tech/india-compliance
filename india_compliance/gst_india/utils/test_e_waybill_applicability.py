import frappe
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
    make_subcontracting_receipt,
)
from frappe.desk.form.load import run_onload
from frappe.tests import IntegrationTestCase, change_settings

from india_compliance.gst_india.overrides.test_asset_movement import create_asset_movement, get_test_asset
from india_compliance.gst_india.overrides.test_subcontracting_transaction import (
    create_subcontracting_data,
    make_sco,
    make_stock_transfer_entry,
)
from india_compliance.gst_india.utils.e_waybill_applicability import (
    get_e_waybill_applicability_reasons,
)
from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_sales_invoice,
    create_transaction,
    make_subcontracting_stock_entry,
)
from india_compliance.tests.erpnext_test_utils import get_rm_items


class TestEWaybillApplicability(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_subcontracting_data()
        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_waybill": 1,
                "enable_e_waybill_from_pi": 1,
                "enable_e_waybill_from_pr": 1,
                "enable_e_waybill_from_dn": 1,
                "enable_e_waybill_for_sc": 1,
                "enable_e_waybill_from_asset_movement": 1,
            },
        )

    def assertApplicability(self, doc, applicable, generatable, reasons=()):
        run_onload(doc)
        self.assertEqual(
            doc.get_onload().e_waybill_applicability,
            {"api_enabled": True, "applicable": applicable, "generatable": generatable},
        )
        self.assertEqual(get_e_waybill_applicability_reasons(doc.doctype, doc.name), list(reasons))

    def test_sales_invoice(self):
        self.assertApplicability(create_sales_invoice(), applicable=True, generatable=True)

        self.assertApplicability(
            create_sales_invoice(item_code="_Test Service Item", gst_hsn_code="999900"),
            applicable=False,
            generatable=False,
            reasons=["All items are service items (HSN code starts with 99)."],
        )

    def test_purchase_invoice(self):
        self.assertApplicability(
            create_purchase_invoice(bill_no="EWB-APPL-1"), applicable=True, generatable=True
        )

        pi = create_purchase_invoice(bill_no="EWB-APPL-2", do_not_submit=True)
        pi.db_set("supplier_address", None)
        self.assertApplicability(
            pi,
            applicable=True,
            generatable=False,
            reasons=["Supplier Address is mandatory to generate e-Waybill."],
        )

    @change_settings("GST Settings", {"enable_e_waybill_from_pi": 0})
    def test_purchase_invoice_switch_off(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-3")
        run_onload(pi)

        self.assertEqual(
            pi.get_onload().e_waybill_applicability,
            {"api_enabled": False, "applicable": False, "generatable": False},
        )
        self.assertEqual(get_e_waybill_applicability_reasons(pi.doctype, pi.name), [])

    def test_purchase_receipt(self):
        self.assertApplicability(
            create_transaction(doctype="Purchase Receipt"), applicable=True, generatable=True
        )

    def test_delivery_note(self):
        self.assertApplicability(
            create_transaction(doctype="Delivery Note"), applicable=True, generatable=True
        )

    def test_stock_entry(self):
        self.assertApplicability(make_subcontracting_stock_entry(), applicable=True, generatable=True)

        same_gstin = make_subcontracting_stock_entry(do_not_submit=True)
        same_gstin.db_set("bill_to_gstin", same_gstin.bill_from_gstin)
        self.assertApplicability(
            same_gstin,
            applicable=False,
            generatable=False,
            reasons=["Bill From GSTIN and Bill To GSTIN are same."],
        )

    def test_asset_movement(self):
        receipt = create_asset_movement(purpose="Receipt", asset=get_test_asset())
        self.assertApplicability(receipt, applicable=True, generatable=True)

        receipt.db_set({"bill_to_gstin": None, "bill_from_address": None})
        self.assertApplicability(
            receipt,
            applicable=False,
            generatable=False,
            reasons=[
                "Bill To GSTIN is not set. Ensure its set in Bill To Address.",
                "Bill From address is mandatory to generate e-Waybill.",
            ],
        )

    def test_subcontracting_receipt(self):
        sco = make_sco()
        make_stock_transfer_entry(sco_no=sco.name, rm_items=get_rm_items(sco.supplied_items))
        scr = make_subcontracting_receipt(sco.name)
        scr.save()
        self.assertApplicability(scr, applicable=True, generatable=True)

        scr.db_set("supplier_address", None)
        self.assertApplicability(
            scr,
            applicable=True,
            generatable=False,
            reasons=["Supplier address is mandatory for e-waybill generation."],
        )

    def test_reasons_only_for_e_waybill_doctypes(self):
        self.assertRaisesRegex(
            frappe.ValidationError,
            "e-Waybill is not supported for Sales Order",
            get_e_waybill_applicability_reasons,
            "Sales Order",
            "any",
        )
