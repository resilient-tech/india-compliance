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
    log_and_process_e_waybill_cancellation,
    log_and_process_e_waybill_generation,
    mark_e_waybill_as_generated,
)
from india_compliance.gst_india.utils.e_waybill_actions import (
    get_e_waybill_applicability_reasons,
    is_e_waybill_auto_cancellable,
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

    def assertApplicability(self, doc, applicable, generatable, reasons=(), required=False):
        run_onload(doc)
        self.assertEqual(
            doc.get_onload().e_waybill_applicability,
            {
                "api_enabled": True,
                "applicable": applicable,
                "generatable": generatable,
                "required": required,
            },
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

    def test_opening_sales_invoice_gets_no_e_waybill_status(self):
        si = create_sales_invoice(is_opening="Yes", rate=100000, do_not_save=True)
        si.items[0].income_account = "Temporary Opening - _TIRC"
        si.insert()
        si.submit()

        # opening entries skip GST validation, so they never reach the e-Waybill status
        self.assertFalse(si.e_waybill_status)

    def test_onload_survives_a_draft_without_company_gstin(self):
        si = create_sales_invoice(rate=100000, do_not_submit=True)
        si.db_set("company_gstin", None)

        si = frappe.get_doc("Sales Invoice", si.name)
        run_onload(si)

        self.assertFalse(si.get_onload().e_waybill_applicability.required)

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

    def mark_generated(self, doc, ewaybill, generated_on, valid_upto=None):
        mark_e_waybill_as_generated(
            doc.doctype,
            doc.name,
            values={
                "ewaybill": ewaybill,
                "e_waybill_date": str(generated_on),
                "valid_upto": str(valid_upto or add_to_date(generated_on, days=1)),
            },
        )
        doc.reload()
        run_onload(doc)

    @change_settings("GST Settings", {"enable_e_waybill_from_pi": 0})
    def test_existing_e_waybill_stays_cancellable_with_the_switch_off(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-5")
        self.mark_generated(pi, "351002721241", now_datetime())

        self.assertTrue(pi.get_onload().e_waybill_info.cancellable)
        self.assertIsNone(pi.get_onload().get("e_waybill_applicability"))

    @change_settings("GST Settings", {"auto_cancel_e_waybill": 1})
    def test_e_waybill_older_than_a_day_is_not_cancellable(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-6")
        self.mark_generated(pi, "351002721242", add_to_date(now_datetime(), days=-2))

        self.assertFalse(pi.get_onload().e_waybill_info.cancellable)
        self.assertFalse(is_e_waybill_auto_cancellable(pi))

    @change_settings("GST Settings", {"auto_cancel_e_waybill": 1, "enable_api": 0})
    def test_auto_cancel_needs_the_api(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-7")
        self.mark_generated(pi, "351002721243", now_datetime())

        self.assertFalse(is_e_waybill_auto_cancellable(pi))

    def test_cancellable_right_after_generation(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-8")
        run_onload(pi)

        log_and_process_e_waybill_generation(
            pi,
            {
                "ewayBillNo": "351002721244",
                "ewayBillDate": str(now_datetime()),
                "validUpto": str(add_to_date(now_datetime(), days=1)),
                "e_waybill_status": "Manually Generated",
            },
        )

        self.assertTrue(pi.get_onload().e_waybill_info.get("cancellable"))

    def test_generatable_right_after_cancellation(self):
        pi = create_purchase_invoice(bill_no="EWB-APPL-9")
        self.mark_generated(pi, "351002721245", now_datetime())

        log_and_process_e_waybill_cancellation(
            pi,
            frappe._dict(reason="Data Entry Mistake"),
            frappe._dict(cancelDate=str(now_datetime()), e_waybill_status="Manually Cancelled"),
        )

        self.assertIsNone(pi.get_onload().get("e_waybill_info"))
        self.assertTrue(pi.get_onload().e_waybill_applicability.generatable)

    def test_e_waybill_validity_window(self):
        for i, (hours, updatable, extendable, extendable_now) in enumerate(
            (
                (10, True, True, False),
                (-1, False, True, True),
                (-9, False, False, False),
            )
        ):
            pi = create_purchase_invoice(bill_no=f"EWB-APPL-1{i}")
            generated_on = add_to_date(now_datetime(), days=-1)
            self.mark_generated(pi, f"35100272125{i}", generated_on, add_to_date(now_datetime(), hours=hours))

            e_waybill_info = pi.get_onload().e_waybill_info
            self.assertEqual(
                (e_waybill_info.updatable, e_waybill_info.extendable, e_waybill_info.extendable_now),
                (updatable, extendable, extendable_now),
                f"valid upto {hours} hours from now",
            )

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

        same_gstin = make_subcontracting_stock_entry(
            do_not_submit=True, bill_to_address="_Test Indian Registered Company-Billing"
        )
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
