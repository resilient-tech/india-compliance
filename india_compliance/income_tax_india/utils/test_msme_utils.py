# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Shared fixtures for the MSME report tests.

Lives here (not next to the 43B(h) report) because that report's folder contains
parentheses - a module path plain ``import`` syntax cannot express.
"""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_transaction,
)
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    FY,
    create_msme_registration,
    create_supplier,
)

COMPANY = "_Test Indian Registered Company"


class MSMEReportTestCase(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_msme_report")
        cls.supplier = cls._create_msme_supplier(enterprise_type="Micro")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_msme_report")

    @classmethod
    def _create_msme_supplier(
        cls, enterprise_type, activity="Manufacturing", financial_year=FY, **msme_kwargs
    ):
        msme = create_msme_registration(
            classifications=[
                {
                    "financial_year": financial_year,
                    "enterprise_type": enterprise_type,
                    "activity": activity,
                }
            ],
            **msme_kwargs,
        )
        return create_supplier(msme.name)

    def _pi(self, supplier, posting_date, rate):
        return create_purchase_invoice(
            supplier=supplier,
            company=COMPANY,
            posting_date=posting_date,
            set_posting_time=1,  # keep the backdated posting_date
            qty=1,
            rate=rate,
        )

    def _pay(self, pi, posting_date, amount=None):
        pe = get_payment_entry("Purchase Invoice", pi.name)
        pe.posting_date = posting_date
        pe.set_posting_time = 1
        pe.reference_no = "TEST"
        pe.reference_date = posting_date
        if amount is not None:
            pe.paid_amount = amount
            pe.references[0].allocated_amount = amount
        pe.insert()
        pe.submit()
        return pe

    def _make_advance(self, supplier, payable_account, posting_date, amount):
        """Payment to the supplier not allocated against any voucher."""
        pe = create_transaction(
            doctype="Payment Entry",
            company=COMPANY,
            payment_type="Pay",
            mode_of_payment="Cash",
            party_type="Supplier",
            party=supplier,
            paid_from=self._get_cash_account(),
            paid_to=payable_account,
            paid_amount=amount,
            posting_date=posting_date,
            set_posting_time=1,
            reference_no="TEST",
            reference_date=posting_date,
            do_not_save=True,
        )
        pe.setup_party_account_field()
        pe.set_missing_values()
        pe.set_exchange_rate()
        pe.received_amount = pe.paid_amount / pe.target_exchange_rate
        pe.save()
        pe.submit()
        return pe

    @staticmethod
    def _get_cash_account():
        return frappe.db.get_value("Company", COMPANY, "default_cash_account") or (
            frappe.db.get_value("Account", {"company": COMPANY, "account_type": "Cash", "is_group": 0})
        )
