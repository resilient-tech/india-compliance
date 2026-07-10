import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils import get_all_gst_accounts
from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_sales_invoice,
)

COMPANY = "_Test Indian Registered Company"


class TestGLEntryValidate(IntegrationTestCase):
    def test_submit_gst_transaction_with_company_gstin(self):
        """A GST transaction with a company GSTIN posts to GST accounts and
        submits without error."""
        si = create_sales_invoice(company=COMPANY, is_in_state=1)

        self.assertTrue(si.company_gstin)
        self.assertEqual(si.docstatus, 1)

    def test_submit_non_gst_transaction(self):
        """A transaction that posts only to non-GST accounts submits without
        error (the GL Entry hook returns early for non-GST accounts)."""
        si = create_sales_invoice(company=COMPANY)

        gst_accounts = get_all_gst_accounts(COMPANY)
        posted_accounts = frappe.get_all("GL Entry", filters={"voucher_no": si.name}, pluck="account")
        self.assertFalse([a for a in posted_accounts if a in gst_accounts])
        self.assertEqual(si.docstatus, 1)

    def test_submit_transaction_without_company_gstin_on_gst_accounts_throws(self):
        si = create_sales_invoice(company=COMPANY, is_in_state=1, do_not_save=1)
        si.company_gstin = ""
        # ignore_mandatory bypasses the transaction-level GSTIN guard so the
        si.insert(ignore_mandatory=True)

        self.assertRaisesRegex(
            frappe.ValidationError,
            "Company GSTIN is a mandatory field for accounting of GST Accounts",
            si.submit,
        )

    def test_cancel_transaction_without_company_gstin_on_gst_accounts(self):
        pinv = create_purchase_invoice(company=COMPANY, is_in_state=1)

        gst_accounts = get_all_gst_accounts(COMPANY)
        gst_gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": pinv.name, "account": ("in", gst_accounts), "is_cancelled": 0},
            pluck="name",
        )
        self.assertTrue(gst_gl_entries)

        # Reproduce the wrong-address state: blank company_gstin on the posted
        for name in gst_gl_entries:
            frappe.db.set_value("GL Entry", name, "company_gstin", None)

        pinv.reload()
        pinv.cancel()

        self.assertEqual(pinv.docstatus, 2)
