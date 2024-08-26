import unittest

import frappe
from frappe.tests.utils import change_settings
from erpnext.accounts.doctype.account.test_account import create_account

from india_compliance.gst_india.utils.tests import append_item, create_purchase_invoice


@change_settings("GST Settings", {"enable_overseas_transactions": 1})
class TestPurchaseInvoice(unittest.TestCase):
    def test_itc_classification(self):
        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_submit=1,
            item_code="_Test Service Item",
        )
        self.assertEqual(pinv.itc_classification, "Import Of Service")

        append_item(pinv)
        pinv.save()
        self.assertEqual(pinv.itc_classification, "Import Of Goods")

        pinv = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            is_reverse_charge=1,
            do_not_submit=1,
        )
        self.assertEqual(pinv.itc_classification, "ITC on Reverse Charge")

        pinv.is_reverse_charge = 0
        pinv.save()
        self.assertEqual(pinv.itc_classification, "All Other ITC")

        company = "_Test Indian Registered Company"
        account = create_account(
            account_name="Unrealized Profit",
            parent_account="Current Assets - _TIRC",
            company=company,
        )

        frappe.db.set_value(
            "Company", company, "unrealized_profit_loss_account", account
        )
        pinv = create_purchase_invoice(
            supplier="Test Internal with ISD Supplier",
            qty=-1,
            is_return=1,
            do_not_submit=1,
        )
        self.assertEqual(pinv.itc_classification, "Input Service Distributor")
