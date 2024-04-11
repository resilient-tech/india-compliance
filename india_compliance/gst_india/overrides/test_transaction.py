import json
import re

from parameterized import parameterized_class

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import today
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import (
    make_regional_gl_entries,
)
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from erpnext.accounts.party import _get_party_details, get_regional_address_details
from erpnext.controllers.accounts_controller import (
    update_child_qty_rate,
    update_gl_dict_with_regional_fields,
)
from erpnext.controllers.taxes_and_totals import get_regional_round_off_accounts
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
    update_regional_gl_entries,
)

from india_compliance.gst_india.constants import SALES_DOCTYPES
from india_compliance.gst_india.overrides.transaction import (
    DOCTYPES_WITH_GST_DETAIL,
    validate_item_tax_template,
)
from india_compliance.gst_india.utils.tests import (
    _append_taxes,
    append_item,
    create_purchase_invoice,
    create_transaction,
)


@parameterized_class(
    ("doctype",),
    [
        ("Purchase Order",),
        ("Purchase Receipt",),
        ("Purchase Invoice",),
        ("Supplier Quotation",),
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
        create_cess_accounts()

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

        if cls.doctype == "Purchase Invoice":
            cls.transaction_details.bill_no = frappe.generate_hash(length=5)

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
        # allowing taxable items with non-taxable items
        doc = create_transaction(**self.transaction_details, do_not_save=True)

        append_item(doc, frappe._dict(item_code="_Test Non GST Item"))

        doc.insert()

    @change_settings(
        "GST Settings",
        {"enable_rcm_for_unregistered_supplier": 1, "rcm_threshold": 5000},
    )
    def test_transaction_with_rcm_to_unregistered_supplier(self):
        if self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            supplier="_Test Unregistered Supplier",
            rate=10000,
        )

        self.assertEqual(doc.is_reverse_charge, 1)
        self.assertEqual(doc.total_taxes_and_charges, 0)
        self.assertDocumentEqual(
            {"account_head": "Input Tax CGST - _TIRC", "base_tax_amount": 900},
            doc.taxes[0],
        )

    def test_non_taxable_items_with_tax(self):
        doc = create_transaction(
            **self.transaction_details,
            is_in_state=True,
            item_tax_template="GST 28% - _TIRC",
            do_not_submit=True,
        )

        for item in doc.items:
            item.gst_treatment = "Nil-Rated"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Cannot charge GST on Non-Taxable Items.*)$"),
            validate_item_tax_template,
            doc,
        )

    def test_validate_item_tax_template(self):
        item_tax_template = frappe.get_doc("Item Tax Template", "GST 28% - _TIRC")
        tax_accounts = item_tax_template.get("taxes")

        # Invalidate item tax template
        item_tax_template.taxes = []
        item_tax_template.flags.ignore_mandatory = True
        item_tax_template.save()

        doc = create_transaction(
            **self.transaction_details,
            is_in_state=True,
            item_tax_template="GST 28% - _TIRC",
            do_not_submit=True,
        )

        for tax in doc.taxes:
            tax.rate = 0

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(No GST is being charged on Taxable Items.*)$"),
            doc.save,
        )

        # Restore item tax template
        item_tax_template.taxes = tax_accounts
        item_tax_template.save()

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

    def test_validate_mandatory_company_address(self):
        def unset_company_gstin():
            doc.set(
                "company_address" if self.is_sales_doctype else "billing_address", ""
            )
            doc.company_gstin = ""

        doc = create_transaction(**self.transaction_details, do_not_submit=True)
        unset_company_gstin()

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(.*to ensure Company GSTIN is fetched in the transaction.*)$"
            ),
            doc.save,
        )

        doc.reload()
        unset_company_gstin()
        doc.flags.ignore_mandatory = True
        doc.save()

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
                "is_sales_item": 0,
            },
        )
        item_without_hsn.insert()
        item_without_hsn.db_set("is_sales_item", 1)

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

    def test_ecommerce_gstin(self):
        doc = create_transaction(**self.transaction_details, do_not_submit=True)
        doc.ecommerce_gstin = "123456789012@ab"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(Invalid E-commerce GSTIN! The check digit validation has failed. Please ensure you've typed the E-commerce GSTIN correctly.*)$"
            ),
            doc.save,
        )

    def test_taxable_value_with_charges(self):
        if self.doctype not in DOCTYPES_WITH_GST_DETAIL:
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
        if self.doctype not in DOCTYPES_WITH_GST_DETAIL:
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

    def test_validate_place_of_supply(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)
        doc.place_of_supply = "96-Others"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*not a valid Place of Supply.*)$"),
            doc.save,
        )

    #######################################################################################
    #            Validate GST Accounts                                                    #
    #######################################################################################
    def test_validate_same_company_and_party_gstin(self):
        doc = create_transaction(
            **self.transaction_details, is_in_state=True, do_not_save=True
        )

        party_gstin_field = (
            "billing_address_gstin" if self.is_sales_doctype else "supplier_gstin"
        )

        doc.company_gstin = "24AAQCA8719H1ZC"
        doc.set(party_gstin_field, doc.company_gstin)

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.* Company GSTIN and Party GSTIN are same)$"),
            doc.insert,
        )

    def test_export_without_payment_of_gst(self):
        if not self.is_sales_doctype:
            return

        frappe.db.set_single_value("GST Settings", "enable_overseas_transactions", 1)
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
        frappe.db.set_single_value("GST Settings", "enable_overseas_transactions", 0)

    def test_reverse_charge_for_sales_transaction(self):
        if not self.is_sales_doctype:
            return

        frappe.db.set_single_value("GST Settings", "enable_reverse_charge_in_sales", 1)
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
        frappe.db.set_single_value("GST Settings", "enable_reverse_charge_in_sales", 0)

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

    def test_invalid_charge_type_as_actual(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)
        _append_taxes(doc, ["CGST", "SGST"], charge_type="Actual", tax_amount=9)

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(.*Charge Type is set to Actual. However, this would not compute item taxes.*)$"
            ),
            doc.save,
        )

    def test_invalid_item_wise_tax_details(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)
        _append_taxes(
            doc,
            ["CGST", "SGST"],
            charge_type="Actual",
            tax_amount=9,
            item_wise_tax_detail=json.dumps({"_Test Trading Goods 1": [9, -9]}),
            dont_recompute_tax=1,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*Charge Type is set to Actual. However, Tax Amount.*)$"),
            doc.save,
        )

    def test_invalid_charge_type_for_cess_non_advol(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)
        _append_taxes(doc, ["CGST", "SGST"], charge_type="On Item Quantity")

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*as it is not a Cess Non Advol Account.*)$"),
            doc.save,
        )

        doc = create_transaction(**self.transaction_details, do_not_save=True)
        _append_taxes(doc, ["CGST", "SGST", "Cess Non Advol"])

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*as it is a Cess Non Advol Account.*)$"),
            doc.save,
        )

    def test_gst_details_set_correctly(self):
        doc = create_transaction(
            **self.transaction_details, rate=200, is_in_state=True, do_not_save=True
        )
        _append_taxes(doc, "Cess Non Advol", charge_type="On Item Quantity", rate=20)
        doc.insert()
        self.assertDocumentEqual(
            {
                "gst_treatment": "Taxable",
                "igst_rate": 0,
                "cgst_rate": 9,
                "sgst_rate": 9,
                "cess_non_advol_rate": 20,
                "igst_amount": 0,
                "cgst_amount": 18,
                "sgst_amount": 18,
                "cess_non_advol_amount": 20,
            },
            doc.items[0],
        )
        append_item(doc, frappe._dict(rate=300))
        doc.save()

        # test same item multiple times
        self.assertDocumentEqual(
            {
                "gst_treatment": "Taxable",
                "igst_rate": 0,
                "cgst_rate": 9,
                "sgst_rate": 9,
                "cess_non_advol_rate": 20,
                "igst_amount": 0,
                "cgst_amount": 27,
                "sgst_amount": 27,
                "cess_non_advol_amount": 20,
            },
            doc.items[1],
        )

        # test non gst treatment
        doc = create_transaction(
            **self.transaction_details, item_code="_Test Non GST Item"
        )
        self.assertDocumentEqual(
            {"gst_treatment": "Non-GST"},
            doc.items[0],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_gst_treatment_for_exports(self):
        if not self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            is_in_state=True,
        )
        self.assertEqual(doc.items[0].gst_treatment, "Taxable")

        # Update Customer after it's already set
        doc_details = {
            **self.transaction_details,
            "customer": "_Test Foreign Customer",
            "party_name": "_Test Foreign Customer",
        }
        doc = create_transaction(**doc_details, do_not_submit=True)
        self.assertEqual(doc.items[0].gst_treatment, "Zero-Rated")

        party_field = "party_name" if self.doctype == "Quotation" else "customer"

        customer = "_Test Registered Customer"
        doc.update(
            {
                party_field: customer,
                **_get_party_details(
                    party=customer,
                    company=doc.company,
                    posting_date=today(),
                    doctype=doc.doctype,
                ),
            }
        )
        doc.selling_price_list = "Standard Selling"
        doc.save()
        self.assertEqual(doc.items[0].gst_treatment, "Taxable")

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_place_of_supply_for_exports(self):
        if not self.is_sales_doctype:
            return

        doc_details = {
            **self.transaction_details,
            "customer": "_Test Foreign Customer",
            "party_name": "_Test Foreign Customer",
            "shipping_address_name": "_Test Registered Customer-Billing",
        }

        doc = create_transaction(**doc_details, is_in_state=True)

        # Place of Supply as Gujarat for Shipping Address in Gujarat
        self.assertEqual(doc.gst_category, "Overseas")
        self.assertEqual(doc.place_of_supply, "24-Gujarat")

    def test_purchase_with_different_place_of_supply(self):
        if self.is_sales_doctype:
            return

        doc = create_transaction(
            **self.transaction_details,
            is_out_state=True,
            do_not_save=True,
        )

        doc.place_of_supply = "27-Maharashtra"
        doc.save()

        # place of supply shouldn't get overwritten
        self.assertEqual(doc.place_of_supply, "27-Maharashtra")

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
            self.transaction_details.customer = self.transaction_details.party_name = (
                "_Test Registered Composition Customer"
            )
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

    def test_invalid_intra_state_supply(self):
        doc = create_transaction(**self.transaction_details, do_not_save=True)

        # Adding CGST Account only
        _append_taxes(doc, "CGST")

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Cannot use only one .* intra-state supplies)$"),
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


class TestQuotationTransaction(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.lead_name = get_lead("_Test Lead")

    def test_quotation_to_lead(self):
        doc = create_transaction(
            doctype="Quotation",
            quotation_to="Lead",
            party_name=self.lead_name,
            company_address="_Test Indian Registered Company-Billing",
        )

        self.assertEqual(doc.gst_category, "Unregistered")


def get_lead(first_name):
    if name := frappe.db.exists("Lead", {"first_name": first_name}):
        return name

    lead = frappe.get_doc(
        {
            "doctype": "Lead",
            "first_name": first_name,
        }
    )
    lead.insert(ignore_permissions=True)

    return lead.name


class TestSpecificTransactions(FrappeTestCase):
    def test_copy_e_waybill_fields_from_dn_to_si(self):
        "Make sure e-Waybill fields are copied from Delivery Note to Sales Invoice"
        dn = create_transaction(doctype="Delivery Note", vehicle_no="GJ01AA1111")
        si = make_sales_invoice(dn.name)

        self.assertEqual(si.vehicle_no, dn.vehicle_no)

    def test_copy_e_waybill_fields_from_si_to_return(self):
        "Make sure e-Waybill fields are not copied from Sales Invoice to Sales Returns"
        si = create_transaction(doctype="Sales Invoice", vehicle_no="GJ01AA1111")
        si_return = make_sales_return(si.name)

        self.assertEqual(si_return.vehicle_no, None)


def create_cess_accounts():
    input_cess_non_advol_account = create_tax_accounts("Input Tax Cess Non Advol")
    output_cess_non_advol_account = create_tax_accounts("Output Tax Cess Non Advol")
    input_cess_account = create_tax_accounts("Input Tax Cess")
    output_cess_account = create_tax_accounts("Output Tax Cess")

    settings = frappe.get_doc("GST Settings")
    for row in settings.gst_accounts:
        if row.company != "_Test Indian Registered Company":
            continue

        if row.account_type == "Input":
            row.cess_account = input_cess_account.name
            row.cess_non_advol_account = input_cess_non_advol_account.name

        if row.account_type == "Output":
            row.cess_account = output_cess_account.name
            row.cess_non_advol_account = output_cess_non_advol_account.name

    settings.save()


def create_tax_accounts(account_name):
    defaults = {
        "company": "_Test Indian Registered Company",
        "doctype": "Account",
        "account_type": "Tax",
        "is_group": 0,
    }

    if "Input" in account_name:
        parent_account = "Tax Assets - _TIRC"
    else:
        parent_account = "Duties and Taxes - _TIRC"

    return frappe.get_doc(
        {
            "account_name": account_name,
            "parent_account": parent_account,
            **defaults,
        }
    ).insert(ignore_if_duplicate=True)


class TestRegionalOverrides(FrappeTestCase):
    @change_settings(
        "GST Settings",
        {"round_off_gst_values": 1},
    )
    def test_get_regional_round_off_accounts(self):

        data = get_regional_round_off_accounts("_Test Indian Registered Company", [])
        self.assertListEqual(
            data,
            [
                "Input Tax CGST - _TIRC",
                "Input Tax SGST - _TIRC",
                "Input Tax IGST - _TIRC",
                "Output Tax CGST - _TIRC",
                "Output Tax SGST - _TIRC",
                "Output Tax IGST - _TIRC",
                "Input Tax CGST RCM - _TIRC",
                "Input Tax SGST RCM - _TIRC",
                "Input Tax IGST RCM - _TIRC",
            ],
        )

    @change_settings(
        "GST Settings",
        {"round_off_gst_values": 0},
    )
    def test_get_regional_round_off_accounts_with_round_off_unchecked(self):

        data = get_regional_round_off_accounts("_Test Indian Registered Company", [])
        self.assertListEqual(data, [])

    def test_update_gl_dict_with_regional_fields(self):

        doc = frappe.get_doc(
            {"doctype": "Sales Invoice", "company_gstin": "29AAHCM7727Q1ZI"}
        )
        gl_entry = {}
        update_gl_dict_with_regional_fields(doc, gl_entry)

        self.assertEqual(gl_entry.get("company_gstin", ""), "29AAHCM7727Q1ZI")

    def test_make_regional_gl_entries(self):
        pi = create_purchase_invoice()
        pi._has_ineligible_itc_items = True

        gl_entries = {"company_gstin": "29AAHCM7727Q1ZI"}
        frappe.flags.through_repost_accounting_ledger = True

        make_regional_gl_entries(gl_entries, pi)

        frappe.flags.through_repost_accounting_ledger = False
        self.assertEqual(pi._has_ineligible_itc_items, False)

    def test_update_regional_gl_entries(self):
        gl_entry = {"company_gstin": "29AAHCM7727Q1ZI"}
        doc = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "is_opening": "Yes",
                "company_gstin": "29AAHCM7727Q1ZI",
            }
        )
        return_entry = update_regional_gl_entries(gl_entry, doc)
        self.assertDictEqual(return_entry, gl_entry)

    def test_get_regional_address_details(self):
        doctype = "Sales Order"
        company = "_Test Indian Registered Company"
        party_details = {
            "customer": "_Test Registered Customer",
            "customer_address": "_Test Registered Customer-Billing",
            "billing_address_gstin": "24AANFA2641L1ZF",
            "gst_category": "Registered Regular",
            "company_gstin": "24AAQCA8719H1ZC",
        }

        get_regional_address_details(party_details, doctype, company)

        self.assertEqual(
            party_details.get("taxes_and_charges"), "Output GST In-state - _TIRC"
        )
        self.assertEqual(party_details.get("place_of_supply"), "24-Gujarat")
        self.assertTrue(party_details.get("taxes"))


class TestItemUpdate(FrappeTestCase):
    DATA = {
        "customer": "_Test Unregistered Customer",
        "item_code": "_Test Trading Goods 1",
        "qty": 1,
        "rate": 100,
        "is_in_state": 1,
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def create_order(self, doctype):
        self.DATA["doctype"] = doctype
        doc = create_transaction(**self.DATA)
        return doc

    def test_so_and_po_after_item_update(self):
        for doctype in ["Sales Order", "Purchase Order"]:
            doc = self.create_order(doctype)

            self.assertDocumentEqual(
                {
                    "taxable_value": 100,
                    "cgst_amount": 9,
                    "sgst_amount": 9,
                },
                doc.items[0],
            )

            # Update Item Rate
            item = doc.items[0]
            item_to_update = [
                {
                    "item_code": item.item_code,
                    "qty": item.qty,
                    "rate": 200,
                    "docname": item.name,
                    "name": item.name,
                    "idx": item.idx,
                }
            ]

            update_child_qty_rate(doctype, json.dumps(item_to_update), doc.name)
            doc = frappe.get_doc(doctype, doc.name)

            self.assertDocumentEqual(
                {
                    "taxable_value": 200,
                    "cgst_amount": 18,
                    "sgst_amount": 18,
                },
                doc.items[0],
            )

            # Insert New Item
            item_to_update.append(
                {"item_code": "_Test Trading Goods 1", "qty": 1, "rate": 50, "idx": 2}
            )

            update_child_qty_rate(doctype, json.dumps(item_to_update), doc.name)
            doc = frappe.get_doc(doctype, doc.name)

            self.assertDocumentEqual(
                {
                    "taxable_value": 50,
                    "cgst_amount": 4.5,
                    "sgst_amount": 4.5,
                },
                doc.items[1],
            )
