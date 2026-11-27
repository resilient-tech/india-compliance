import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.report.accounts_payable.accounts_payable import execute as accounts_payable
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.utils.payment_ledger import (
    CREDIT_NOTE,
    PAYMENT,
    WRITE_OFF,
    get_unallocated,
    get_voucher_ledgers,
)

COMPANY = "_Test Indian Registered Company"
PAYABLE = "Creditors - _TIRC"
WRITE_OFF_ACCOUNT = "Write Off - _TIRC"


class TestPaymentLedger(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_payment_ledger")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_payment_ledger")

    def setUp(self):
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = f"_Test Ledger Supplier {frappe.generate_hash(length=6)}"
        supplier.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0})
        self.supplier = supplier.insert().name

    def test_settlements_match_accounts_payable(self):
        bill = self.create_bill(days_ago=60)
        self.pay(bill, 400, days_ago=30)
        self.pay(bill, 200, days_ago=8).cancel()
        self.pay(bill, 100, days_ago=-5)
        self.journal(100, days_ago=20, voucher_type="Bank Entry", bill=bill)
        self.journal(50, days_ago=10, voucher_type="Write Off Entry", bill=bill)
        debit_note = self.return_against(bill, days_ago=5)
        self.journal(30, days_ago=3, voucher_type="Bank Entry", bill=debit_note, party_side="credit")
        self.advance(250, days_ago=15)

        ledgers = self.get_ledgers()
        ledger = ledgers[("Purchase Invoice", bill.name, self.supplier)]

        self.assertEqual(ledger.balance_on(), 380)
        self.assertEqual(ledger.balance_on(add_days(today(), -25)), 600)
        self.assertEqual(ledger.settled(kinds=[PAYMENT]), 470)
        self.assertEqual(ledger.settled(kinds=[WRITE_OFF]), 50)
        self.assertEqual(ledger.settled(kinds=[CREDIT_NOTE]), 100)
        self.assertEqual(ledger.settled(to_date=add_days(today(), -25)), 400)
        self.assertIsNone(ledger.paid_on())
        self.assertEqual(get_unallocated(ledgers), {self.supplier: 250})
        self.assertEqual(get_unallocated(ledgers, add_days(today(), -20)), {})
        self.assert_matches_accounts_payable(ledgers)
        self.assert_matches_accounts_payable(ledgers, add_days(today(), -25))

        ledgers = get_voucher_ledgers(COMPANY, vouchers=[("Purchase Invoice", bill.name)])
        self.assertEqual(list(ledgers), [("Purchase Invoice", bill.name, self.supplier)])
        self.assertEqual(ledgers[("Purchase Invoice", bill.name, self.supplier)].balance_on(), 380)

    def test_write_offs_returns_and_journal_bills(self):
        bill = self.create_bill(
            days_ago=50,
            write_off_amount=100,
            write_off_account=WRITE_OFF_ACCOUNT,
            write_off_cost_center="Main - _TIRC",
        )
        self.pay(bill, 900, days_ago=35)
        self.return_against(
            bill,
            days_ago=30,
            update_outstanding_for_self=1,
            write_off_amount=-10,
            write_off_account=WRITE_OFF_ACCOUNT,
            write_off_cost_center="Main - _TIRC",
        )

        debit_note = self.create_bill(days_ago=25, is_return=1, qty=-2, update_outstanding_for_self=0)
        journal_bill = self.journal(1000, days_ago=40, voucher_type="Journal Entry")
        for amount, days_ago in ((333.33, 20), (333.33, 18), (333.34, 15)):
            self.journal(amount, days_ago=days_ago, voucher_type="Bank Entry", bill=journal_bill)

        ledgers = self.get_ledgers()
        ledger = ledgers[("Purchase Invoice", bill.name, self.supplier)]
        self.assertEqual(ledger.settled(kinds=[WRITE_OFF]), 100)
        self.assertEqual(ledger.settled(kinds=[PAYMENT]), 900)
        # ERPNext posts a self-outstanding return's write-off against the original bill, reopening it
        self.assertEqual(ledger.balance_on(), 10)
        self.assertEqual(ledger.balance_on(add_days(today(), -35)), 0)
        self.assertIsNone(ledger.paid_on())

        ledger = ledgers[("Journal Entry", journal_bill.name, self.supplier)]
        self.assertEqual(ledger.settled(kinds=[PAYMENT]), 1000)
        self.assertEqual(ledger.balance_on(), 0)
        self.assertEqual(ledger.paid_on(), getdate(add_days(today(), -15)))

        self.assertIn(("Purchase Invoice", debit_note.name, self.supplier), ledgers)
        self.assertEqual(get_unallocated(ledgers), {self.supplier: 300})
        self.assert_matches_accounts_payable(ledgers)

    def test_from_date_keeps_earlier_settlements(self):
        old_bill = self.create_bill(days_ago=60)
        bill = self.create_bill(days_ago=20)
        self.pay(bill, 300, days_ago=30)
        self.return_against(old_bill, days_ago=5)

        ledgers = get_voucher_ledgers(COMPANY, from_date=add_days(today(), -25), parties=[self.supplier])
        self.assertEqual(list(ledgers), [("Purchase Invoice", bill.name, self.supplier)])
        self.assertEqual(ledgers[("Purchase Invoice", bill.name, self.supplier)].balance_on(), 700)

        old_bill_key = ("Purchase Invoice", old_bill.name)
        self.assertFalse(
            get_voucher_ledgers(COMPANY, from_date=add_days(today(), -25), vouchers=[old_bill_key])
        )
        ledgers = get_voucher_ledgers(COMPANY, from_date=add_days(today(), -60), vouchers=[old_bill_key])
        self.assertEqual(ledgers[(*old_bill_key, self.supplier)].balance_on(), 900)

        # before the bill exists the report shows its payment as an advance; the supplier's total agrees
        before_bill = add_days(today(), -25)
        self.assertEqual(get_unallocated(self.get_ledgers(), before_bill), {self.supplier: 300})
        outstanding = self.get_outstanding(before_bill)
        self.assertEqual(sum(value for value in outstanding.values() if value < 0), -300)

    def get_ledgers(self):
        return get_voucher_ledgers(COMPANY, parties=[self.supplier])

    def assert_matches_accounts_payable(self, ledgers, report_date=None):
        balances = {
            ledger.voucher_no: ledger.balance_on(report_date)
            for ledger in ledgers.values()
            if ledger.balance_on(report_date)
        }
        self.assertEqual(balances, self.get_outstanding(report_date))

    def get_outstanding(self, report_date=None):
        report = accounts_payable(
            {
                "company": COMPANY,
                "party_type": "Supplier",
                "party": [self.supplier],
                "report_date": report_date or today(),
                "range": "30, 60, 90, 120",
            }
        )[1]
        return {row.get("voucher_no"): row.get("outstanding") for row in report if row.get("outstanding")}

    def create_bill(self, days_ago, **kwargs):
        posting_date = add_days(today(), -days_ago)
        return create_purchase_invoice(
            supplier=self.supplier,
            posting_date=posting_date,
            bill_date=posting_date,
            set_posting_time=1,
            **{"qty": 10, "rate": 100, **kwargs},
        )

    def pay(self, bill, amount, days_ago):
        payment = get_payment_entry("Purchase Invoice", bill.name)
        payment.posting_date = add_days(today(), -days_ago)
        payment.paid_amount = payment.received_amount = amount
        payment.references[0].allocated_amount = amount
        payment.reference_no = "LEDGER-TEST"
        payment.reference_date = payment.posting_date
        return payment.insert().submit()

    def advance(self, amount, days_ago):
        payment = frappe.new_doc("Payment Entry")
        payment.update(
            {
                "payment_type": "Pay",
                "company": COMPANY,
                "posting_date": add_days(today(), -days_ago),
                "party_type": "Supplier",
                "party": self.supplier,
                "paid_from": "Cash - _TIRC",
                "paid_to": PAYABLE,
                "paid_amount": amount,
                "received_amount": amount,
                "reference_no": "LEDGER-ADVANCE",
                "reference_date": add_days(today(), -days_ago),
            }
        )
        payment.insert().submit()

    def journal(self, amount, days_ago, voucher_type, bill=None, party_side=None):
        """Debit the supplier against `bill`, or without one credit the supplier as a bill."""
        posting_date = add_days(today(), -days_ago)
        entry = frappe.new_doc("Journal Entry")
        entry.update(
            {
                "company": COMPANY,
                "voucher_type": voucher_type,
                "posting_date": posting_date,
                "cheque_no": "LEDGER-TEST",
                "cheque_date": posting_date,
            }
        )
        party_side = party_side or ("debit" if bill else "credit")
        side = f"{party_side}_in_account_currency"
        other_side = "credit_in_account_currency" if party_side == "debit" else "debit_in_account_currency"
        entry.append(
            "accounts",
            {
                "account": PAYABLE,
                "party_type": "Supplier",
                "party": self.supplier,
                side: amount,
                "reference_type": bill and bill.doctype,
                "reference_name": bill and bill.name,
            },
        )
        other_account = {
            "Write Off Entry": WRITE_OFF_ACCOUNT,
            "Journal Entry": "Cost of Goods Sold - _TIRC",
        }.get(voucher_type, "Cash - _TIRC")
        entry.append("accounts", {"account": other_account, other_side: amount})
        return entry.insert().submit()

    def return_against(self, bill, days_ago, **kwargs):
        debit_note = make_return_doc("Purchase Invoice", bill.name)
        debit_note.posting_date = add_days(today(), -days_ago)
        debit_note.set_posting_time = 1
        debit_note.update({"update_outstanding_for_self": 0, **kwargs})
        debit_note.items[0].qty = -1
        debit_note.calculate_taxes_and_totals()
        return debit_note.insert().submit()
