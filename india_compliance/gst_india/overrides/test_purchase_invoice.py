import frappe
from frappe.tests import IntegrationTestCase, change_settings
from erpnext.accounts.doctype.account.test_account import create_account

from india_compliance.gst_india.utils.tests import append_item, create_purchase_invoice


class TestPurchaseInvoice(IntegrationTestCase):
    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
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
        )
        self.assertEqual(pinv.itc_classification, "Input Service Distributor")

        pinv = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_save=1,
            is_reverse_charge=1,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            "Reverse Charge is not applicable on Import of Goods",
            pinv.save,
        )

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

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            "Transaction Name must be 16 characters or fewer to meet GST requirements",
            pinv.save,
        )
