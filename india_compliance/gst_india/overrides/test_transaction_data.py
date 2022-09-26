import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, getdate

from india_compliance.gst_india.utils.tests import create_sales_invoice
from india_compliance.gst_india.utils.transaction_data import (
    GSTTransactionData,
    validate_non_gst_items,
)


class TestTransactionData(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_transaction_data")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_transaction_data")

    @classmethod
    def setUp(cls):
        pass

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

    def test_validate_non_gst_items(self):
        doc = create_sales_invoice(item_code="_Test Non GST Item", do_not_submit=True)
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*transactions with non-GST items)$"),
            validate_non_gst_items,
            doc,
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
            re.compile(r"^(PIN Code.* a 6-digit number.*)$"),
            GSTTransactionData(doc).check_missing_address_fields,
            address,
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
        # ToDo: assert for dict equal
        # doc = create_sales_invoice(do_not_submit=True)
        # GSTTransactionData(doc).set_transaction_details
        pass

    def test_set_transporter_details(self):
        # ToDo: assert for dict equal
        pass

    def test_get_all_item_details(self):
        pass
