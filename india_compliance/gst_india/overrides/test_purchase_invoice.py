import re

import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils.tests import create_purchase_invoice


class TestPurchaseInvoice(FrappeTestCase):
    def test_validate_invoice_length(self):
        # No error for registered supplier
        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            is_reverse_charge=True,
            do_not_save=True,
        )
        setattr(pinv, "__newname", "INV/2022/00001/asdfsadf")  # NOQA
        pinv.meta.autoname = "prompt"
        pinv.save()

        # Error for unregistered supplier
        pinv = create_purchase_invoice(
            supplier="_Test Unregistered Supplier",
            is_reverse_charge=True,
            do_not_save=True,
        )
        setattr(pinv, "__newname", "INV/2022/00001/asdfsadg")  # NOQA
        pinv.meta.autoname = "prompt"

        pinv.save()

        self.assertEqual(
            frappe.parse_json(frappe.message_log[-1]).get("message"),
            "Transaction Name must be 16 characters or fewer to meet GST requirements",
        )
<<<<<<< HEAD
=======

        # Reset autoname (as it's cached)
        pinv.meta.autoname = "naming_series:"

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    @change_settings("GST Settings", {"validate_hsn_code": 0})
    def test_validate_hsn_code_for_overseas(self):
        frappe.db.set_value("Item", "_Test Service Item", "gst_hsn_code", "")
        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_submit=1,
            do_not_save=1,
            item_code="_Test Service Item",
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST HSN Code is mandatory for Overseas Purchase Invoice.*)"),
            pinv.save,
        )

        frappe.db.set_value("Item", "_Test Service Item", "gst_hsn_code", "999900")
>>>>>>> 44fe923b (fix: validate hsn code for Overseas purchase invoice)
