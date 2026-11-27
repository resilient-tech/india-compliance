import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from india_compliance.gst_india.utils.tests import create_transaction
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    create_msme_registration,
    create_supplier,
)
from india_compliance.income_tax_india.utils.msme import get_indian_fiscal_year

COMPANY = "_Test Indian Registered Company"


class TestMSMETransactions(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_msme_transactions")
        cls.bill_date = add_days(today(), -10)
        cls.micro = create_supplier(cls.create_registration("Micro"))
        cls.medium = create_supplier(cls.create_registration("Medium"))

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_msme_transactions")

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

    def test_journal_entry_bill(self):
        [message] = self.saved_messages(self.journal_entry(self.micro, due_in=60), "MSME Due Date")
        self.assertEqual(message["primary_action"]["args"]["doctype"], "Journal Entry")
        self.assertEqual(
            message["primary_action"]["args"]["due_date"], str(getdate(add_days(self.bill_date, 45)))
        )

        self.assertFalse(self.saved_messages(self.journal_entry(self.micro, due_in=45), "MSME Due Date"))
        self.assertFalse(self.saved_messages(self.journal_entry(self.micro, due_in=None), "MSME Due Date"))
        self.assertFalse(self.saved_messages(self.journal_entry(self.medium, due_in=60), "MSME Due Date"))

    def test_purchase_order_terms(self):
        self.assertTrue(self.saved_messages(self.purchase_order(self.micro, due_in=60), "MSME Payment Terms"))
        self.assertFalse(
            self.saved_messages(self.purchase_order(self.micro, due_in=45), "MSME Payment Terms")
        )
        self.assertFalse(
            self.saved_messages(self.purchase_order(self.medium, due_in=60), "MSME Payment Terms")
        )

    def journal_entry(self, supplier, due_in):
        entry = frappe.new_doc("Journal Entry")
        entry.update(
            {
                "company": COMPANY,
                "posting_date": self.bill_date,
                "bill_date": self.bill_date,
                "due_date": add_days(self.bill_date, due_in) if due_in is not None else None,
            }
        )
        entry.append(
            "accounts",
            {"account": "Cost of Goods Sold - _TIRC", "debit_in_account_currency": 1000},
        )
        entry.append(
            "accounts",
            {
                "account": "Creditors - _TIRC",
                "party_type": "Supplier",
                "party": supplier,
                "credit_in_account_currency": 1000,
            },
        )
        return entry

    def purchase_order(self, supplier, due_in):
        order = create_transaction(
            doctype="Purchase Order",
            supplier=supplier,
            transaction_date=self.bill_date,
            schedule_date=self.bill_date,
            do_not_save=1,
        )
        order.append(
            "payment_schedule",
            {"due_date": add_days(self.bill_date, due_in), "invoice_portion": 100},
        )
        return order

    def saved_messages(self, doc, title):
        frappe.clear_messages()
        doc.insert()
        return [message for message in frappe.get_message_log() if message.get("title") == title]
