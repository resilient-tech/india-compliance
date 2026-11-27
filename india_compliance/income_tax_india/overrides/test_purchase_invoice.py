import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, format_date, getdate, today

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    create_msme_registration,
    create_supplier,
)
from india_compliance.income_tax_india.utils.msme import get_indian_fiscal_year, resolve_msme_status


class TestPurchaseInvoiceOverride(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_income_tax_purchase_invoice")
        cls.bill_date = add_days(today(), -10)
        cls.micro = create_supplier(cls.create_registration("Micro"))
        cls.medium = create_supplier(cls.create_registration("Medium"))

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_income_tax_purchase_invoice")

    @staticmethod
    def create_registration(enterprise_type):
        return create_msme_registration(
            classifications=[
                {
                    "financial_year": get_indian_fiscal_year(add_days(today(), -400)),
                    "enterprise_type": enterprise_type,
                }
            ]
        ).name

    def test_msme_due_date_message(self):
        limit = add_days(self.bill_date, 45)

        [message] = self.get_messages(self.create_bill(self.micro, due_in=60))
        self.assertEqual(message["primary_action"]["args"]["due_date"], str(getdate(limit)))

        self.assertFalse(self.get_messages(self.create_bill(self.micro, due_in=45)))
        self.assertFalse(self.get_messages(self.create_bill(self.medium, due_in=60)))

        bill = self.create_bill(self.micro, due_in=30)
        bill.due_date = add_days(self.bill_date, 50)
        bill.payment_schedule = []
        self.assertTrue(self.save_and_get_messages(bill))
        self.assertFalse(self.save_and_get_messages(bill))

    def test_msme_status(self):
        bill = self.create_bill(self.micro, due_in=60)
        status = resolve_msme_status(bill)["msme_status"]

        self.assertIn("MSME supplier (Micro)", status)
        self.assertIn(format_date(add_days(self.bill_date, 45)), status)

        order = frappe._dict(doctype="Purchase Order", supplier=self.micro, transaction_date=today())
        self.assertNotIn("pay by", resolve_msme_status(order)["msme_status"])
        self.assertIn(
            "not covered",
            resolve_msme_status(
                frappe._dict(doctype="Purchase Order", supplier=self.medium, transaction_date=today())
            )["msme_status"],
        )
        self.assertIsNone(
            resolve_msme_status(frappe._dict(doctype="Purchase Order", supplier="_Test Registered Supplier"))[
                "msme_status"
            ]
        )

    def create_bill(self, supplier, due_in):
        frappe.clear_messages()
        return create_purchase_invoice(
            supplier=supplier,
            posting_date=self.bill_date,
            bill_date=self.bill_date,
            due_date=add_days(self.bill_date, due_in),
            set_posting_time=1,
            do_not_submit=1,
        )

    def get_messages(self, bill):
        return [message for message in frappe.get_message_log() if message.get("title") == "MSME Due Date"]

    def save_and_get_messages(self, bill):
        frappe.clear_messages()
        bill.save()
        return self.get_messages(bill)
