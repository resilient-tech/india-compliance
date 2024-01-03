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
            "docs": [],
        },
        {
            "doc_num": 4,
            "doc_typ": "Debit Note",
            "docs": [],
        },
        {
            "doc_num": 5,
            "doc_typ": "Credit Note",
            "docs": [],
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
        filters = {
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "from_date": getdate(),
            "to_date": getdate(),
            "type_of_business": "Document Issued Summary",
        }
        report_data = format_data_to_dict(execute(filters))

        report_json = get_json(
            "Document Issued Summary", "24AAQCA8719H1ZC", report_data, filters
        )

        self.assertDictEqual(report_json, JSON_OUTPUT)


def create_test_items():
    """Create Sales Invoices for testing GSTR1 Document Issued Summary."""

    invoices_for_outward_supply = JSON_OUTPUT["doc_det"][0]["docs"]
    debit_notes = JSON_OUTPUT["doc_det"][1]["docs"]
    credit_notes = JSON_OUTPUT["doc_det"][2]["docs"]

    # Sales Invoices
    sales_invoices = create_sales_invoices(3)
    create_sales_invoices(1)[0].cancel()
    sales_invoice = create_sales_invoices(1, do_not_save=True, do_not_submit=True)[
        0
    ].save()

    invoices_for_outward_supply.append(
        {
            "num": 1,
            "to": sales_invoice.name,
            "from": sales_invoices[0].name,
            "totnum": 5,
            "cancel": 2,
            "net_issue": 3,
        }
    )

    # Credit Notes
    sales_invoices = create_sales_invoices(3, is_return=1, qty=-1)
    create_sales_invoices(1, is_return=1, qty=-1)[0].cancel()
    sales_invoice = create_sales_invoices(
        1, is_return=1, qty=-1, do_not_save=True, do_not_submit=True
    )[0].save()

    credit_notes.append(
        {
            "num": 1,
            "to": sales_invoice.name,
            "from": sales_invoices[0].name,
            "totnum": 5,
            "cancel": 2,
            "net_issue": 3,
        }
    )

    # Sales Invoices with Non GST Items
    # Excluded from Document Issued Summary
    create_sales_invoices(3, item_code="_Test Non GST Item")

    # Debit Notes
    sales_invoices = create_sales_invoices(5, is_debit_note=1)

    debit_notes.append(
        {
            "num": 1,
            "to": sales_invoices[-1].name,
            "from": sales_invoices[0].name,
            "totnum": 5,
            "cancel": 0,
            "net_issue": 5,
        }
    )

    # Opening Entry
    # Excluded from Document Issued Summary
    create_opening_entry().submit()

    # Sales Invoice with Same Billing GSTIN
    # Excluded from Document Issued Summary
    sales_invoice = create_sales_invoices(1, do_not_submit=True)[0]
    sales_invoice.customer_address = sales_invoice.company_address
    sales_invoice.save()
    sales_invoice.submit()

    # Sales Invoices
    sales_invoices = create_sales_invoices(5)

    invoices_for_outward_supply.append(
        {
            "num": 2,
            "to": sales_invoices[-1].name,
            "from": sales_invoices[0].name,
            "totnum": 5,
            "cancel": 0,
            "net_issue": 5,
        }
    )


def create_sales_invoices(count, **kwargs):
    """Create a list of sales invoices."""
    return [create_sales_invoice(**kwargs) for _ in range(count)]


def create_opening_entry():
    sales_invoice = frappe.new_doc("Sales Invoice")
    sales_invoice.update(
        {
            "company": "_Test Indian Registered Company",
            "is_opening": "Yes",
            "against_income_account": "Temporary Opening - _TIRC",
            "items": [
                {
                    "item_code": "_Test Trading Goods 1",
                    "item_name": "_Test Trading Goods 1",
                    "qty": 1,
                    "income_account": "Temporary Opening - _TIRC",
                }
            ],
            "customer": "_Test Registered Customer",
        }
    )

    sales_invoice.save()

    return sales_invoice
