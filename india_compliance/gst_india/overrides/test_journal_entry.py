import re

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe.tests import IntegrationTestCase, change_settings

from india_compliance.gst_india.overrides.journal_entry import is_link_used_as_reference_only
from india_compliance.gst_india.utils.tests import (
    create_itc_reclaim_journal_entry,
    create_itc_reversal_journal_entry,
    create_purchase_invoice,
)


class TestJournalEntry(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # New company with a single GSTIN (no linked addresses).
        # The make_company_fixtures hook auto-creates GST accounts
        # and registers them in GST Settings.
        cls.company_name = "_Test JE Company"
        cls.company = frappe.new_doc("Company")
        cls.company_gstin = "27AAQCA8719H1Z6"
        cls.company.update(
            {
                "company_name": cls.company_name,
                "abbr": "_TJEC",
                "country": "India",
                "default_currency": "INR",
                "domain": "Manufacturing",
                "chart_of_accounts": "Standard",
                "enable_perpetual_inventory": 0,
                "gstin": cls.company_gstin,
                "gst_category": "Registered Regular",
            }
        )
        cls.company.insert()

        cls.multi_gstin_company_name = "_Test Indian Registered Company"
        cls._create_company_address(
            cls.multi_gstin_company_name,
            gstin="27AAQCA8719H1Z6",
            address_title="_Test JE Multi GSTIN Billing",
        )

    @classmethod
    def _create_company_address(cls, company, gstin, address_title):
        address = frappe.new_doc("Address")
        address.address_title = address_title
        address.address_type = "Billing"
        address.address_line1 = "Test Address"
        address.city = "Mumbai"
        address.state = "Maharashtra"
        address.country = "India"
        address.pincode = "400001"
        address.gstin = gstin
        address.gst_category = "Registered Regular"
        address.append("links", {"link_doctype": "Company", "link_name": company})
        address.insert()

    def test_auto_set_company_gstin_for_single_linked_gstin(self):
        """
        When a company has exactly one GSTIN and company_gstin is not set on
        the Journal Entry, validate() should auto-populate company_gstin.
        """
        doc = create_itc_reversal_journal_entry(
            company=self.company_name,
            tax_amount=9,
            do_not_submit=True,
        )
        self.assertEqual(doc.company_gstin, self.company_gstin)

    def test_validate_mandatory_company_gstin_if_multiple_gstins(self):
        """
        When a company has multiple GSTINs and company_gstin is not set on the
        Journal Entry, validate() should raise a ValidationError.
        """

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"Company GSTIN is mandatory if any GST account is present\."),
            create_itc_reversal_journal_entry,
            company=self.multi_gstin_company_name,
            tax_amount=9,
        )

    def test_gst_tax_type_set_in_journal_entry(self):
        """
        Validate that gst_tax_type is correctly set for each account row in a Journal Entry.
        """
        doc = create_itc_reversal_journal_entry(
            company=self.company_name,
            tax_amount=9,
            do_not_submit=True,
        )

        # accounts[0] is GST Expense (None), accounts[1] is CGST, accounts[2] is SGST
        self.assertEqual(doc.accounts[1].gst_tax_type, "cgst")
        self.assertEqual(doc.accounts[2].gst_tax_type, "sgst")

    def test_itc_journal_entry_links_purchase_invoice_without_settling_it(self):
        """A linked reversal or reclaim fails to submit or rewrites the invoice outstanding."""
        invoice = create_purchase_invoice(is_in_state=1)
        reversal = self._submit_itc_entry_linked_to_invoice(create_itc_reversal_journal_entry, invoice)

        invoice.reload()
        self.assertEqual(invoice.outstanding_amount, 118)
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_no": reversal.name, "against_voucher": invoice.name})
        )

        get_payment_entry("Purchase Invoice", invoice.name).submit()
        self._submit_itc_entry_linked_to_invoice(create_itc_reclaim_journal_entry, invoice)
        reversal.cancel()

        invoice.reload()
        self.assertEqual(invoice.outstanding_amount, 0)
        self.assertEqual(invoice.status, "Paid")

    def test_itc_journal_entry_skips_party_and_account_check(self):
        """A linked ITC row fails the invoice's party and account check."""
        invoice = create_purchase_invoice(is_in_state=1)

        def entry_with_gst_rows_linked_to_invoice(voucher_type):
            entry = create_itc_reversal_journal_entry(
                tax_amount=9, company_gstin=invoice.company_gstin, do_not_submit=True
            )
            entry.voucher_type = voucher_type
            for row in entry.accounts[1:]:
                row.reference_type = "Purchase Invoice"
                row.reference_name = invoice.name

            return entry

        self.assertRaisesRegex(
            frappe.ValidationError,
            "Party / Account does not match",
            entry_with_gst_rows_linked_to_invoice("Journal Entry").save,
        )
        entry_with_gst_rows_linked_to_invoice("Reversal Of ITC").save()

    @change_settings("Accounts Settings", {"unlink_payment_on_cancellation_of_invoice": 1})
    def test_invoice_linked_in_itc_entry_cannot_be_cancelled(self):
        """Cancelling the invoice drops the link from its ITC reversal."""
        invoice = create_purchase_invoice(is_in_state=1)
        reversal = self._submit_itc_entry_linked_to_invoice(create_itc_reversal_journal_entry, invoice)

        self.assertRaisesRegex(
            frappe.ValidationError, f"Cancel ITC Journal Entry {reversal.name}", invoice.cancel
        )
        self.assertEqual(
            frappe.db.count(
                "Journal Entry Account",
                {"parent": reversal.name, "reference_name": invoice.name},
            ),
            2,
        )

    def test_itc_journal_entry_rejects_draft_invoice(self):
        """An ITC entry can link a draft invoice."""
        draft = create_purchase_invoice(is_in_state=1, do_not_submit=True)
        self.assertRaisesRegex(
            frappe.ValidationError,
            "is not submitted",
            self._submit_itc_entry_linked_to_invoice,
            create_itc_reversal_journal_entry,
            draft,
        )

    def test_itc_link_only_for_registered_company(self):
        """An unregistered company's ITC entry skips ERPNext's reference checks and ours."""
        doc = frappe._dict(voucher_type="Reversal Of ITC", company="_Test Indian Unregistered Company")
        row = frappe._dict(reference_type="Purchase Invoice")
        self.assertFalse(is_link_used_as_reference_only(doc, row))

        doc.company = "_Test Indian Registered Company"
        self.assertTrue(is_link_used_as_reference_only(doc, row))

    def _submit_itc_entry_linked_to_invoice(self, create_itc_entry, invoice):
        entry = create_itc_entry(tax_amount=9, company_gstin=invoice.company_gstin, do_not_submit=True)
        for row in entry.accounts[1:]:
            row.reference_type = "Purchase Invoice"
            row.reference_name = invoice.name

        entry.submit()
        return entry
