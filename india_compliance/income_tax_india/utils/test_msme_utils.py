# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Shared fixtures for the MSME report tests."""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    FY,
    create_msme_registration,
    create_supplier,
)

COMPANY = "_Test Indian Registered Company"

# test records: both Micro/Manufacturing for FY 2023-2024. The second has no
# written agreement on payment terms, so supplies to it carry the 15-day limit
# u/s 15 rather than 45.
MSME_SUPPLIER = "_Test MSME Supplier"
MSME_SUPPLIER_WITHOUT_AGREEMENT = "_Test MSME Supplier without Agreement"


class MSMEReportTestCase(IntegrationTestCase):
    supplier = MSME_SUPPLIER

    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_msme_report")

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

    def _pi(self, supplier, posting_date, rate, **kwargs):
        return create_purchase_invoice(
            supplier=supplier,
            company=COMPANY,
            posting_date=posting_date,
            set_posting_time=1,  # keep the backdated posting_date
            qty=1,
            rate=rate,
            **kwargs,
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
