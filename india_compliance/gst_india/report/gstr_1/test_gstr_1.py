import random

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from india_compliance.gst_india.report.gstr_1.gstr_1 import (
    GSTR1DocumentIssuedSummary,
    execute,
    format_data_to_dict,
    get_json,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice

JSON_OUTPUT = {
    "doc_det": [
        {
            "doc_num": 1,
            "doc_typ": "Invoices for outward supply",
            "docs": [
                {
                    "num": 1,
                    "to": "SINV-23-00005",
                    "from": "SINV-23-00001",
                    "totnum": 5,
                    "cancel": 4,
                    "net_issue": 1,
                },
                {
                    "num": 2,
                    "to": "SINV-23-00020",
                    "from": "SINV-23-00016",
                    "totnum": 5,
                    "cancel": 3,
                    "net_issue": 2,
                },
            ],
        },
        {
            "doc_num": 4,
            "doc_typ": "Debit Note",
            "docs": [
                {
                    "num": 1,
                    "to": "SINV-23-00015",
                    "from": "SINV-23-00011",
                    "totnum": 5,
                    "cancel": 3,
                    "net_issue": 2,
                }
            ],
        },
        {
            "doc_num": 5,
            "doc_typ": "Credit Note",
            "docs": [
                {
                    "num": 1,
                    "to": "SINV-23-00010",
                    "from": "SINV-23-00006",
                    "totnum": 5,
                    "cancel": 1,
                    "net_issue": 4,
                }
            ],
        },
    ]
}


class TestGSTR1DocumentIssuedSummary(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_test_items()

    def test_is_same_naming_series(self):
        doc_summary = GSTR1DocumentIssuedSummary({})

        test_cases = [
            ("00483-SINV-23", "00484-SINV-23", True),
            ("00483-SINV-23", "00485-SINV-23", False),
            ("SINV-0005-23", "SINV-0006-23", True),
            ("SINV-0005-23", "00006-SINV-23", False),
            ("SINV-0005-23", "SINV-0006-24", False),
            ("INV-23-001", "INV-23-002", True),
            ("INV-23-001", "INV-23-111", False),
            ("SINV-10-23-001", "SINV-11-23-001", True),
        ]

        for test_case in test_cases:
            self.assertEqual(
                doc_summary.is_same_naming_series(test_case[0], test_case[1]),
                test_case[2],
            )

    def test_get_document_issued_summary_json(self):
        report_data = format_data_to_dict(
            execute(
                {
                    "company": "_Test Indian Registered Company",
                    "company_gstin": "24AAQCA8719H1ZC",
                    "from_date": getdate(),
                    "to_date": getdate(),
                    "type_of_business": "Document Issued Summary",
                }
            )
        )

        report_json = get_json(
            "Document Issued Summary", "24AAQCA8719H1ZC", report_data
        )

        self.assertDictEqual(report_json, JSON_OUTPUT)


def create_test_items():
    """Create Sales Invoices for testing GSTR1 Document Issued Summary."""

    sales_invoices = create_sales_invoices(30)

    for i in range(len(sales_invoices)):
        if 5 <= i < 10:
            # Credit Notes
            sales_invoices[i].is_return = 1
            sales_invoices[i].items[0].qty = -1
        elif 10 <= i < 15:
            # Debit Notes
            sales_invoices[i].is_debit_note = 1
        elif 20 <= i < 25:
            # Sales Invoices with non GST Items
            # Excluded from Document Issued Summary
            sales_invoices[i].items[0].item_code = "_Test Non GST Item"
            sales_invoices[i].items[0].item_name = "_Test Non GST Item"
        elif 25 <= i < 30:
            # Sales Invoices with same GSTIN Billing
            # Excluded from Document Issued Summary
            sales_invoices[i].save()
            sales_invoices[i].customer_address = sales_invoices[i].company_address

    # Opening Entry
    # Excluded from Document Issued Summary
    sales_invoices.append(create_opening_entry())

    # Setting seed to 1 to get same random action for each test run
    random.seed(1)

    for sales_invoice in sales_invoices:
        action = random.choice(["save", "submit", "cancel"])
        if action == "save":
            sales_invoice.save()
        elif action == "submit":
            sales_invoice.save()
            sales_invoice.submit()
        elif action == "cancel":
            sales_invoice.save()
            sales_invoice.submit()
            sales_invoice.cancel()


def create_sales_invoices(count):
    """Create a list of sales invoices."""
    return [
        create_sales_invoice(do_not_save=True, do_not_submit=True) for _ in range(count)
    ]


def create_opening_entry():
    sales_invoice = frappe.new_doc("Sales Invoice")
    sales_invoice.update(
        {
            "company": "_Test Indian Registered Company",
            "is_opening": "Yes",
            "items": [
                {
                    "item_code": "_Test Trading Goods 1",
                    "item_name": "_Test Trading Goods 1",
                    "qty": 1,
                }
            ],
            "customer": "_Test Registered Customer",
        }
    )
    sales_invoice.save()

    return sales_invoice
