import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.utils.tests import (
    create_itc_reversal_journal_entry,
    create_journal_entry,
)


class TestJournalEntry(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.savepoint("before_test_journal_entry")

        # New company with a single GSTIN (no linked addresses).
        # The make_company_fixtures hook auto-creates GST accounts
        # and registers them in GST Settings.
        cls.company = frappe.new_doc("Company")
        cls.gstin = "27AAQCA8719H1Z6"
        cls.company.update(
            {
                "company_name": "_Test JE Company",
                "abbr": "_TJEC",
                "country": "India",
                "default_currency": "INR",
                "domain": "Manufacturing",
                "chart_of_accounts": "Standard",
                "enable_perpetual_inventory": 0,
                "gstin": cls.gstin,
                "gst_category": "Registered Regular",
            }
        )
        cls.company.insert()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_journal_entry")

    def test_auto_set_company_gstin_for_single_linked_gstin(self):
        """
        When a company has exactly one GSTIN and company_gstin is not set on
        the Journal Entry, validate() should auto-populate company_gstin.
        """
        doc = create_itc_reversal_journal_entry(
            company="_Test JE Company",
            tax_amount=9,
            do_not_submit=True,
        )
        self.assertEqual(doc.company_gstin, "27AAQCA8719H1Z6")

    def test_validate_mandatory_company_gstin_if_multiple_gstins(self):
        """
        When a company has multiple GSTINs and company_gstin is not set on the
        Journal Entry, validate() should raise a ValidationError.
        """
        # Ensure company has multiple GSTINs via addresses
        frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": "Second Address",
                "address_type": "Billing",
                "address_line1": "Line 1",
                "city": "Mumbai",
                "state": "Maharashtra",
                "country": "India",
                "gstin": "27AAQCA8719H1Z6",
                "links": [{"link_doctype": "Company", "link_name": "_Test Indian Registered Company"}],
            }
        ).insert()

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"Company GSTIN is mandatory if any GST account is present\."),
            create_itc_reversal_journal_entry,
            company="_Test Indian Registered Company",
            tax_amount=9,
        )

    def test_gst_tax_type_set_in_journal_entry(self):
        """
        Validate that gst_tax_type is correctly set for each account row in a Journal Entry.
        """
        doc = create_itc_reversal_journal_entry(
            company="_Test Indian Registered Company",
            tax_amount=9,
            do_not_submit=True,
        )

        # accounts[0] is GST Expense (None), accounts[1] is CGST, accounts[2] is SGST
        self.assertEqual(doc.accounts[1].gst_tax_type, "cgst")
        self.assertEqual(doc.accounts[2].gst_tax_type, "sgst")
