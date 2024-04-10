import re

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_to_date, getdate
from frappe.utils.data import format_date
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import (
    make_regional_gl_entries,
)
from erpnext.controllers.accounts_controller import update_gl_dict_with_regional_fields
from erpnext.controllers.taxes_and_totals import get_regional_round_off_accounts
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
    update_regional_gl_entries,
)

from india_compliance.gst_india.utils.tests import (
    _append_taxes,
    append_item,
    create_purchase_invoice,
    create_sales_invoice,
)
from india_compliance.gst_india.utils.transaction_data import GSTTransactionData


class TestTransactionData(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_transaction_data")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_transaction_data")

    def test_validate_mode_of_transport(self):
        doc = create_sales_invoice(do_not_save=True)

        doc.mode_of_transport = ""

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*Mode of Transport is required to.*)$"),
            GSTTransactionData(doc).validate_mode_of_transport,
        )

        doc.mode_of_transport = "Road"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Vehicle Number is required to.*)$"),
            GSTTransactionData(doc).validate_mode_of_transport,
        )

        doc.update({"mode_of_transport": "Ship", "vehicle_no": "GJ07DL9009"})

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Vehicle Number and L/R No is required.*)$"),
            GSTTransactionData(doc).validate_mode_of_transport,
        )

        doc.mode_of_transport = "Rail"
        doc.save()
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(L/R No. is required to generate.*)$"),
            GSTTransactionData(doc).validate_mode_of_transport,
        )

    def test_check_missing_address_fields(self):
        doc = create_sales_invoice(do_not_submit=True)

        address = frappe.get_doc("Address", "_Test Registered Customer-Billing")
        address.address_title = ""

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*is missing in Address.*)$"),
            GSTTransactionData(doc).check_missing_address_fields,
            address,
        )

        address.address_title = "_Test Registered Customer"
        address.pincode = "025923"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(Postal Code for Address.* must be a 6-digit number and cannot start with 0)$"
            ),
            GSTTransactionData(doc).check_missing_address_fields,
            address,
        )

    def test_get_address_details(self):
        doc = create_sales_invoice()

        self.assertDictEqual(
            GSTTransactionData(doc).get_address_details(doc.customer_address),
            {
                "gstin": "24AANFA2641L1ZF",
                "state_number": "24",
                "address_title": "Test Registered Customer",
                "address_line1": "Test Address - 3",
                "address_line2": None,
                "city": "Test City",
                "pincode": 380015,
                "country_code": None,
            },
        )

    def test_validate_transaction(self):
        post_date = add_to_date(getdate(), days=1)

        doc = create_sales_invoice(
            posting_date=post_date, set_posting_time=True, do_not_submit=True
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Posting Date.*Today's Date)$"),
            GSTTransactionData(doc).validate_transaction,
        )

        doc.update(
            {
                "posting_date": getdate(),
                "lr_no": "12345",
                "lr_date": add_to_date(getdate(), days=-2),
            }
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Posting Date.*LR Date)$"),
            GSTTransactionData(doc).validate_transaction,
        )

    def test_set_transaction_details(self):
        """Check transaction data"""
        doc = create_sales_invoice(
            do_not_submit=True,
            is_in_state=True,
        )

        gst_transaction_data = GSTTransactionData(doc)
        gst_transaction_data.set_transaction_details()

        self.assertDictEqual(
            gst_transaction_data.transaction_details,
            {
                "company_name": "_Test Indian Registered Company",
                "party_name": "_Test Registered Customer",
                "date": format_date(frappe.utils.today(), "dd/mm/yyyy"),
                "total": 100.0,
                "total_taxable_value": 100.0,
                "total_non_taxable_value": 0.0,
                "rounding_adjustment": 0.0,
                "grand_total": 118.0,
                "grand_total_in_foreign_currency": "",
                "discount_amount": 0,
                "company_gstin": "24AAQCA8719H1ZC",
                "name": doc.name,
                "total_cgst_amount": 9.0,
                "total_sgst_amount": 9.0,
                "total_igst_amount": 0,
                "total_cess_amount": 0,
                "total_cess_non_advol_amount": 0,
                "other_charges": 0.0,
            },
        )

    def test_set_transaction_details_with_other_charges(self):
        doc = create_sales_invoice(do_not_submit=True)
        _append_taxes(doc, ("CGST", "SGST"))

        tds = {
            "charge_type": "On Previous Row Total",
            "row_id": "2",
            "account_head": "TDS Payable - _TIRC",
            "description": "TDS ON SALES",
            "rate": "1",
            "cost_center": "Main - _TIRC",
        }

        doc.append("taxes", tds)
        doc.save()

        gst_transaction_data = GSTTransactionData(doc)
        gst_transaction_data.set_transaction_details()

        self.assertDictEqual(
            gst_transaction_data.transaction_details,
            {
                "company_name": "_Test Indian Registered Company",
                "party_name": "_Test Registered Customer",
                "date": format_date(frappe.utils.today(), "dd/mm/yyyy"),
                "total": 100.0,
                "total_taxable_value": 100.0,
                "total_non_taxable_value": 0.0,
                "rounding_adjustment": -0.18,
                "grand_total": 119.0,
                "grand_total_in_foreign_currency": "",
                "discount_amount": 0,
                "company_gstin": "24AAQCA8719H1ZC",
                "name": doc.name,
                "other_charges": 1.18,
                "total_cgst_amount": 9.0,
                "total_sgst_amount": 9.0,
                "total_igst_amount": 0,
                "total_cess_amount": 0,
                "total_cess_non_advol_amount": 0,
            },
        )

    def test_set_transporter_details(self):
        """Dict Assertion for transporter details"""
        doc = create_sales_invoice(vehicle_no="GJ07DL9009", do_not_submit=True)

        gst_transaction_data = GSTTransactionData(doc)
        gst_transaction_data.set_transporter_details()

        self.assertDictEqual(
            gst_transaction_data.transaction_details,
            {
                "distance": 0,
                "mode_of_transport": 1,
                "vehicle_type": "R",
                "vehicle_no": "GJ07DL9009",
                "lr_no": None,
                "lr_date": "",
                "gst_transporter_id": "",
                "transporter_name": "",
            },
        )

    def test_get_all_item_details(self):
        """Assertion for all Item Details fetched from transaction docs"""
        doc = create_sales_invoice(do_not_submit=True)

        self.assertListEqual(
            GSTTransactionData(doc).get_all_item_details(),
            [
                {
                    "item_no": 1,
                    "qty": 1.0,
                    "taxable_value": 100.0,
                    "hsn_code": "61149090",
                    "item_name": "Test Trading Goods 1",
                    "uom": "NOS",
                    "cgst_amount": 0,
                    "cgst_rate": 0,
                    "sgst_amount": 0,
                    "sgst_rate": 0,
                    "igst_amount": 0,
                    "igst_rate": 0,
                    "cess_amount": 0,
                    "cess_rate": 0,
                    "cess_non_advol_amount": 0,
                    "cess_non_advol_rate": 0,
                    "tax_rate": 0.0,
                    "total_value": 100.0,
                    "gst_treatment": "Nil-Rated",
                }
            ],
        )

        # Test with grouping of same items
        append_item(doc, frappe._dict(item_code="_Test Trading Goods 1"))
        _append_taxes(doc, ("CGST", "SGST"))
        doc.group_same_items = True
        doc.save()

        self.assertListEqual(
            GSTTransactionData(doc).get_all_item_details(),
            [
                {
                    "item_no": 1,
                    "qty": 2.0,
                    "taxable_value": 200.0,
                    "hsn_code": "61149090",
                    "item_name": "Test Trading Goods 1",
                    "uom": "NOS",
                    "cgst_amount": 18.0,
                    "cgst_rate": 9.0,
                    "sgst_amount": 18.0,
                    "sgst_rate": 9.0,
                    "igst_amount": 0,
                    "igst_rate": 0,
                    "cess_amount": 0,
                    "cess_rate": 0,
                    "cess_non_advol_amount": 0,
                    "cess_non_advol_rate": 0,
                    "tax_rate": 18.0,
                    "total_value": 236.0,
                    "gst_treatment": "Taxable",
                }
            ],
        )

    def test_validate_unique_hsn_and_uom(self):
        doc = create_sales_invoice(do_not_submit=True)

        append_item(doc, frappe._dict(item_code="_Test Trading Goods 1", uom="Box"))

        doc.group_same_items = True

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Row #.*Grouping of items is not possible.)$"),
            doc.submit,
        )

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
        self.assertListEqual(
            data,
            [],
        )

    def test_update_gl_dict_with_regional_fields(self):

        doc = frappe.get_doc(
            {"doctype": "Sales Order", "company_gstin": "29AAHCM7727Q1ZI"}
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
                "doctype": "Sales Order",
                "is_opening": "Yes",
                "company_gstin": "29AAHCM7727Q1ZI",
            }
        )
        return_entry = update_regional_gl_entries(gl_entry, doc)
        self.assertDictEqual(
            return_entry,
            gl_entry,
        )
