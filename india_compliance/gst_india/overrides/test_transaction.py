import re

from parameterized import parameterized_class

import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.constants import SALES_DOCTYPES
from india_compliance.gst_india.overrides.transaction import DOCTYPES_WITH_TAXABLE_VALUE
from india_compliance.gst_india.utils.tests import (
    _append_taxes,
    append_item,
    create_transaction,
)


@parameterized_class(
    ("doctype",),
    [
        ("Purchase Order",),
        ("Purchase Receipt",),
        ("Purchase Invoice",),
        ("Quotation",),
        ("Sales Order",),
        ("Delivery Note",),
        ("Sales Invoice",),
        # TODO: Fix in ERPNext
        # ("POS Invoice"),
    ],
)
class TestTransaction(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_transaction")
        cls.is_sales_doctype = cls.doctype in SALES_DOCTYPES

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_transaction")

    @classmethod
    def setUp(cls):
        cls.transaction_details = frappe._dict(doctype=cls.doctype)
        if cls.doctype == "Quotation":
            cls.transaction_details.party_name = "_Test Registered Customer"

            # Hack. Avoid failing validations as quotation does not have customer field
            cls.transaction_details.customer = "_Test Registered Customer"

    def test_transaction_for_unregistered_company(self):
        if self.is_sales_doctype:
            self.transaction_details.customer = "_Test Registered Customer"
        else:
            self.transaction_details.supplier = "_Test Registered Supplier"

        doc = create_transaction(
            **self.transaction_details,
            company="_Test Indian Unregistered Company",
            gst_category="Unregistered",
        )

        # No validation error should occur for unregistered customers
        self.assertDocumentEqual({"gst_category": "Unregistered", "taxes": []}, doc)

    def test_transaction_for_foreign_company(self):
        if self.is_sales_doctype:
            self.transaction_details.customer = "_Test Registered Customer"
        else:
            self.transaction_details.supplier = "_Test Registered Supplier"

        doc = create_transaction(
            **self.transaction_details,
            company="_Test Foreign Company",
            gst_category="Unregistered",
            currency="USD",
        )

        # No validation error should occur for unregistered customers
        self.assertDocumentEqual({"gst_category": "Unregistered", "taxes": []}, doc)

    def test_transaction_with_gst_and_non_gst_items(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)

        append_item(doc, frappe._dict(item_code="_Test Non GST Item"))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Items not covered under GST cannot be clubbed.*)$"),
            doc.insert,
        )

    def test_transaction_for_items_with_duplicate_taxes(self):
        # Should not allow same item in invoice with multiple taxes
        doc = create_transaction(**self.transaction_details, do_not_save=True)

        append_item(doc, frappe._dict(item_tax_template="GST 28% - _TIRC"))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Cannot use different Item Tax Templates in different.*)$"),
            doc.insert,
        )

    def test_place_of_supply_is_set(self):
        doc = create_transaction(**self.transaction_details)

        self.assertTrue(doc.place_of_supply)

    def test_validate_mandatory_company_gstin(self):
        doc = create_transaction(**self.transaction_details, do_not_submit=True)

        if self.is_sales_doctype:
            doc.company_address = ""
        else:
            doc.billing_address = ""

        doc.company_gstin = ""

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*is a mandatory field for GST Transactions.*)$"),
            doc.save,
        )

    def test_validate_mandatory_gst_category(self):
        doc = create_transaction(**self.transaction_details, do_not_submit=True)

        if self.is_sales_doctype:
            address = doc.customer_address
            doc.customer_address = ""
        else:
            address = doc.supplier_address
            doc.supplier_address = ""

        frappe.db.set_value("Address", address, "gst_category", "")
        gst_category = doc.gst_category
        doc.gst_category = ""

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*is a mandatory field for GST Transactions.*)$"),
            doc.save,
        )

        frappe.db.set_value("Address", address, "gst_category", gst_category)

    def test_validate_overseas_gst_category(self):
        # GST Setting is disabled by default.

        if self.is_sales_doctype:
            self.transaction_details.customer_address = (
                "_Test Registered Customer-Billing-1"
            )
        else:
            self.transaction_details.supplier_address = (
                "_Test Registered Supplier-Billing-1"
            )

        doc = create_transaction(**self.transaction_details, do_not_save=True)
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST Category cannot be set to.*)$"),
            doc.insert,
        )

    def test_missing_hsn_code(self):
        if not self.is_sales_doctype:
            return

        # GST Setting is enabled by default.

        # create item
        item_without_hsn = frappe.new_doc("Item")
        item_without_hsn.update(
            {
                "description": "_Test Item Without HSN",
                "is_stock_item": 1,
                "item_code": "_Test Item Without HSN",
                "item_name": "_Test Item Without HSN",
                "valuation_rate": 100,
            },
        )
        item_without_hsn.flags.ignore_validate = True
        item_without_hsn.insert()

        # create transaction
        doc = create_transaction(
            **self.transaction_details,
            item_code="_Test Item Without HSN",
            do_not_submit=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Please enter a valid HSN/SAC code for.*)$"),
            doc.submit,
        )

    def test_invalid_hsn_digits(self):
        if not self.is_sales_doctype:
            return

        # default GST Setting is 6 digits.
        doc = create_transaction(**self.transaction_details, do_not_submit=True)

        doc.items[0].gst_hsn_code = "12345"
        doc.save()
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Please enter a valid HSN/SAC code for.*)$"),
            doc.submit,
        )

    def test_reverse_charge_transaction(self):
        if self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            supplier="_Test Unregistered Supplier",
            is_reverse_charge=1,
            is_in_state_rcm=True,
            do_not_submit=True,
        )

        doc.taxes[0].rate = 18

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Booked reverse charge is not equal to.*)$"),
            doc.save,
        )

    def test_validate_gst_category_unregistered(self):
        doc = create_transaction(**self.transaction_details, do_not_submit=True)

        if self.is_sales_doctype:
            address = doc.customer_address
        else:
            address = doc.supplier_address

        frappe.db.set_value("Address", address, "gst_category", "Unregistered")
        doc.gst_category = "Unregistered"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST Category cannot be Unregistered.*)$"),
            doc.save,
        )

        frappe.db.set_value("Address", address, "gst_category", "Registered Regular")

    def test_gst_category_with_invalid_regex(self):
        doc = create_transaction(**self.transaction_details, do_not_submit=True)

        if self.is_sales_doctype:
            address = doc.customer_address
        else:
            address = doc.supplier_address

        frappe.db.set_value("Address", address, "gst_category", "UIN Holders")
        doc.gst_category = "UIN Holders"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(The GSTIN you've entered doesn't match.*)$"),
            doc.save,
        )

        frappe.db.set_value("Address", address, "gst_category", "Registered Regular")

    def test_gst_category_without_gstin(self):
        doc = create_transaction(**self.transaction_details, do_not_submit=True)

        if self.is_sales_doctype:
            address = doc.customer_address
            gstin = doc.billing_address_gstin
        else:
            address = doc.supplier_address
            gstin = doc.supplier_gstin

        frappe.db.set_value("Address", address, "gstin", "")

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST Category should be one of.*)$"),
            doc.save,
        )

        frappe.db.set_value("Address", address, "gstin", gstin)

    def test_taxable_value_with_charges(self):
        if self.doctype not in DOCTYPES_WITH_TAXABLE_VALUE:
            return

        doc = create_transaction(**self.transaction_details, do_not_save=True)

        # Adding charges
        doc.append(
            "taxes",
            {
                "charge_type": "Actual",
                "account_head": "Freight and Forwarding Charges - _TIRC",
                "description": "Freight",
                "tax_amount": 20,
                "cost_center": "Main - _TIRC",
            },
        )

        # Adding taxes
        _append_taxes(
            doc, ("CGST", "SGST"), charge_type="On Previous Row Total", row_id=1
        )
        doc.insert()

        self.assertDocumentEqual({"taxable_value": 120}, doc.items[0])  # 100 + 20

    def test_taxable_value_with_charges_after_tax(self):
        if self.doctype not in DOCTYPES_WITH_TAXABLE_VALUE:
            return

        doc = create_transaction(
            **self.transaction_details, is_in_state=True, do_not_save=True
        )

        # Adding charges
        doc.append(
            "taxes",
            {
                "charge_type": "Actual",
                "account_head": "Freight and Forwarding Charges - _TIRC",
                "description": "Freight",
                "tax_amount": 20,
                "cost_center": "Main - _TIRC",
            },
        )
        doc.insert()
        self.assertDocumentEqual({"taxable_value": 100}, doc.items[0])

    #######################################################################################
    #            Validate GST Accounts                                                    #
    #######################################################################################

    def test_export_without_payment_of_gst(self):
        if not self.is_sales_doctype:
            return

        frappe.db.set_value("GST Settings", None, "enable_overseas_transactions", 1)
        # default is_export_with_gst is 0
        doc = create_transaction(
            **self.transaction_details,
            customer_address="_Test Registered Customer-Billing-1",
            is_out_state=1,
            do_not_save=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*since export is without.*)$"),
            doc.insert,
        )
        frappe.db.set_value("GST Settings", None, "enable_overseas_transactions", 0)

    def test_reverse_charge_for_sales_transaction(self):
        if not self.is_sales_doctype:
            return

        frappe.db.set_value("GST Settings", None, "enable_reverse_charge_in_sales", 1)
        doc = create_transaction(
            **self.transaction_details,
            is_reverse_charge=1,
            is_in_state=True,
            do_not_save=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*since supply is under reverse charge.*)$"),
            doc.insert,
        )
        frappe.db.set_value("GST Settings", None, "enable_reverse_charge_in_sales", 0)

    def test_purchase_from_composition_dealer(self):
        if self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            supplier="_Test Registered Composition Supplier",
            is_out_state=True,
            do_not_save=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*registered under Composition Scheme.*)$"),
            doc.insert,
        )

    def test_purchase_with_reverse_charge_account(self):
        if self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            supplier="_Test Registered Supplier",
            is_in_state_rcm=True,
            do_not_save=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Cannot use Reverse Charge Account.*)$"),
            doc.insert,
        )

    def test_purchase_from_unregistered_supplier(self):
        if self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            supplier="_Test Unregistered Supplier",
            is_in_state=True,
            do_not_save=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*purchase is from a Supplier without GSTIN.*)$"),
            doc.insert,
        )

    def test_purchase_with_different_place_of_supply(self):
        if self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            is_out_state=True,
            do_not_save=True,
        )

        doc.place_of_supply = "96-Other Countries"
        doc.save()

        # place of supply shouldn't get overwritten
        self.assertEqual(doc.place_of_supply, "96-Other Countries")

        # IGST should get applied
        self.assertIn("IGST", doc.taxes[-1].description)

    def test_invalid_gst_account_type(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)
        doc.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": (
                    f"{'Input' if self.is_sales_doctype else 'Output'} Tax IGST - _TIRC"
                ),
                "description": "IGST",
                "rate": 18,
                "cost_center": "Main - _TIRC",
            },
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*not a valid GST account.*)$"),
            doc.insert,
        )

    def test_invalid_gst_account_outstate(self):
        doc = create_transaction(
            **self.transaction_details, is_out_state=True, do_not_save=True
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*Cannot charge IGST for intra-state.*)$"),
            doc.insert,
        )

    def test_invalid_gst_account_instate(self):
        if self.is_sales_doctype:
            self.transaction_details.customer = (
                self.transaction_details.party_name
            ) = "_Test Registered Composition Customer"
        else:
            self.transaction_details.supplier = "_Test Registered InterState Supplier"

        doc = create_transaction(
            **self.transaction_details, is_in_state=True, do_not_save=True
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*Cannot charge CGST/SGST for inter-state.*)$"),
            doc.insert,
        )

    def test_invalid_charge_type_in_taxes(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)

        # Adding charges
        doc.append(
            "taxes",
            {
                "charge_type": "Actual",
                "account_head": "Freight and Forwarding Charges - _TIRC",
                "description": "Freight",
                "tax_amount": 20,
                "cost_center": "Main - _TIRC",
            },
        )

        # Adding taxes
        _append_taxes(
            doc, ("CGST", "SGST"), charge_type="On Previous Row Amount", row_id=1
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*Charge Type cannot be.*)$"),
            doc.insert,
        )

    def test_invalid_row_id_for_taxes(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)

        # Adding charges
        doc.append(
            "taxes",
            {
                "charge_type": "Actual",
                "account_head": "Freight and Forwarding Charges - _TIRC",
                "description": "Freight",
                "tax_amount": 20,
                "cost_center": "Main - _TIRC",
            },
        )

        # Adding taxes
        _append_taxes(doc, "CGST", charge_type="On Previous Row Total", row_id=1)
        _append_taxes(doc, "SGST", charge_type="On Previous Row Total", row_id=2)

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*Only one row can be selected as a Reference Row.*)$"),
            doc.insert,
        )
