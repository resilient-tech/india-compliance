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
