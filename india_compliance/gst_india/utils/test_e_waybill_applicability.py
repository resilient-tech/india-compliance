import frappe
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
    make_subcontracting_receipt,
)
from frappe.desk.form.load import run_onload
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import add_to_date, now_datetime

from india_compliance.exceptions import NotApplicableError
from india_compliance.gst_india.overrides.test_asset_movement import create_asset_movement, get_test_asset
from india_compliance.gst_india.overrides.test_subcontracting_transaction import (
    create_subcontracting_data,
    make_sco,
    make_stock_transfer_entry,
)
from india_compliance.gst_india.utils.e_waybill import (
    EWaybillData,
    can_auto_cancel_e_waybill,
    mark_e_waybill_as_generated,
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
            {"api_enabled": True, "applicable": applicable, "generatable": generatable, "cancellable": False},
        )
        self.assertEqual(get_e_waybill_applicability_reasons(doc.doctype, doc.name), list(reasons))

    def test_sales_invoice(self):
        self.assertApplicability(create_sales_invoice(), applicable=True, generatable=True)

        self.assertApplicability(
            create_sales_invoice(item_code="_Test Service Item", gst_hsn_code="999900"),
            applicable=False,
            generatable=False,
            reasons=["e-Waybill cannot be generated because all items have service HSN codes"],
        )

    def test_purchase_invoice(self):
        self.assertApplicability(
            create_purchase_invoice(bill_no="EWB-APPL-1"), applicable=True, generatable=True
        )

        pi = create_purchase_invoice(bill_no="EWB-APPL-2", do_not_submit=True)
        pi.db_set({"supplier_address": None, "bill_no": None})
        self.assertApplicability(
            pi,
            applicable=True,
            generatable=False,
            reasons=[
                f"{pi.meta.get_label('supplier_address')} is required to generate e-Waybill",
                "Bill No is mandatory to generate e-Waybill for Purchase Invoice",
            ],
        )

    @change_settings("GST Settings", {"enable_e_waybill_from_pi": 0})
    def test_purchase_invoice_switch_off(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-3")
        run_onload(pi)

        self.assertIsNone(pi.get_onload().get("e_waybill_applicability"))
        self.assertEqual(get_e_waybill_applicability_reasons(pi.doctype, pi.name), [])

    @change_settings("GST Settings", {"enable_e_waybill_from_pi": 0})
    def test_generation_needs_the_doctype_switch(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-4")

        self.assertRaisesRegex(
            NotApplicableError,
            "e-Waybill is not applicable for this Purchase Invoice",
            EWaybillData(pi).validate_applicability,
        )

    def mark_generated(self, doc, ewaybill, generated_on):
        mark_e_waybill_as_generated(
            doc.doctype,
            doc.name,
            values={
                "ewaybill": ewaybill,
                "e_waybill_date": str(generated_on),
                "valid_upto": str(add_to_date(generated_on, days=1)),
            },
        )
        doc.reload()
        run_onload(doc)

    @change_settings("GST Settings", {"enable_e_waybill_from_pi": 0})
    def test_existing_e_waybill_stays_cancellable_with_the_switch_off(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-5")
        self.mark_generated(pi, "351002721241", now_datetime())

        self.assertTrue(pi.get_onload().e_waybill_applicability.cancellable)

    @change_settings("GST Settings", {"auto_cancel_e_waybill": 1})
    def test_e_waybill_older_than_a_day_is_not_cancellable(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-6")
        self.mark_generated(pi, "351002721242", add_to_date(now_datetime(), days=-2))

        self.assertFalse(pi.get_onload().e_waybill_applicability.cancellable)
        self.assertFalse(can_auto_cancel_e_waybill(pi))

    @change_settings("GST Settings", {"auto_cancel_e_waybill": 1, "enable_api": 0})
    def test_auto_cancel_needs_the_api(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-7")
        self.mark_generated(pi, "351002721243", now_datetime())

        self.assertFalse(can_auto_cancel_e_waybill(pi))

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
            reasons=["e-Waybill cannot be generated because party GSTIN is same as company GSTIN"],
        )

    def test_asset_movement(self):
        receipt = create_asset_movement(purpose="Receipt", asset=get_test_asset())
        self.assertApplicability(receipt, applicable=True, generatable=True)

        receipt.db_set({"bill_to_gstin": None, "bill_from_address": None})
        self.assertApplicability(
            receipt,
            applicable=True,
            generatable=False,
            reasons=[
                f"{receipt.meta.get_label('bill_to_gstin')} is not set. Ensure it's set in the Company Address.",
                f"{receipt.meta.get_label('bill_from_address')} is required to generate e-Waybill",
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
            reasons=[f"{scr.meta.get_label('supplier_address')} is required to generate e-Waybill"],
        )

    def test_reasons_only_for_e_waybill_doctypes(self):
        self.assertRaisesRegex(
            frappe.ValidationError,
            "e-Waybill is not supported for Sales Order",
            get_e_waybill_applicability_reasons,
            "Sales Order",
            "any",
        )
