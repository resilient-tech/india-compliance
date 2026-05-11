import re

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.tests import (
    create_itc_reversal_journal_entry,
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
