import json

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import getdate

from india_compliance.gst_india.report.gstr_1.gstr_1 import (
    GSTR1DocumentIssuedSummary,
    execute,
    format_data_to_dict,
    get_b2cl_json,
    get_gstr1_json,
    get_json,
)
from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_sales_invoice,
)

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
        {
            "doc_num": 2,
            "doc_typ": "Invoices for inward supply from unregistered person",
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

        report_json = get_json("Document Issued Summary", "24AAQCA8719H1ZC", report_data, filters)

        self.assertDictEqual(report_json, JSON_OUTPUT)


class TestGSTR1B2B(FrappeTestCase):
    def test_get_gstr1_json_for_b2b(self):
        invoice_1 = create_sales_invoice(
            customer="_Test Registered Customer",
            customer_address="_Test Registered Customer-Billing",
            place_of_supply="29-Karnataka",
            is_out_state=True,
        )

        invoice_2 = create_sales_invoice(
            customer="_Test Registered Customer",
            customer_address="_Test Registered Customer-Billing",
            place_of_supply="24-Gujarat",
            is_in_state=True,
        )

        self.addCleanup(invoice_1.cancel)
        self.addCleanup(invoice_2.cancel)

        filters = {
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "from_date": str(getdate()),
            "to_date": str(getdate()),
            "type_of_business": "B2B",
        }
        result = get_gstr1_json(json.dumps(filters))

        # Assert result structure
        self.assertIn("file_name", result)
        self.assertIn("data", result)
        self.assertIn("b2b", result["data"])

        b2b_data = result["data"]["b2b"]
        self.assertIsInstance(b2b_data, list)
        self.assertGreater(len(b2b_data), 0)

        # Get customer data
        customer_gstin = invoice_1.billing_address_gstin
        customer_data = next((item for item in b2b_data if item["ctin"] == customer_gstin), None)
        self.assertIsNotNone(customer_data, f"Customer with GSTIN {customer_gstin} not found")
        self.assertIn("inv", customer_data)

        # Get specific invoices from result
        invoices = customer_data["inv"]
        invoice_1_data = next((inv for inv in invoices if inv["inum"] == invoice_1.name), None)
        invoice_2_data = next((inv for inv in invoices if inv["inum"] == invoice_2.name), None)

        self.assertIsNotNone(invoice_1_data, f"Invoice {invoice_1.name} not found in B2B data")
        self.assertIsNotNone(invoice_2_data, f"Invoice {invoice_2.name} not found in B2B data")

        # Assert invoice 1 structure (Karnataka - POS 29)
        self.assertEqual(invoice_1_data["pos"], "29")
        self.assertEqual(invoice_1_data["rchrg"], "N")
        self.assertEqual(invoice_1_data["inv_typ"], "R")
        self.assertGreater(len(invoice_1_data["itms"]), 0)

        invoice_1_item = invoice_1_data["itms"][0]
        self.assertEqual(invoice_1_item["num"], 1)
        item_det_1 = invoice_1_item["itm_det"]
        self.assertIn("txval", item_det_1)
        self.assertIn("rt", item_det_1)
        self.assertEqual(item_det_1["rt"], 18.0)

        # Verify tax amounts are present and positive
        total_tax_1 = item_det_1.get("iamt", 0) + item_det_1.get("camt", 0) + item_det_1.get("samt", 0)
        self.assertGreater(total_tax_1, 0, "Invoice should have tax amount")

        # Assert invoice 2 structure (Gujarat - POS 24)
        self.assertEqual(invoice_2_data["pos"], "24")
        self.assertEqual(invoice_2_data["rchrg"], "N")
        self.assertEqual(invoice_2_data["inv_typ"], "R")
        self.assertGreater(len(invoice_2_data["itms"]), 0)

        invoice_2_item = invoice_2_data["itms"][0]
        self.assertEqual(invoice_2_item["num"], 1)
        item_det_2 = invoice_2_item["itm_det"]
        self.assertIn("txval", item_det_2)
        self.assertIn("rt", item_det_2)
        self.assertEqual(item_det_2["rt"], 18.0)

        # Verify tax amounts are present and positive
        total_tax_2 = item_det_2.get("iamt", 0) + item_det_2.get("camt", 0) + item_det_2.get("samt", 0)
        self.assertGreater(total_tax_2, 0, "Invoice should have tax amount")


class TestGSTR1B2CL(FrappeTestCase):
    def test_b2cl_item_num_resets_per_invoice(self):
        gstin = "24AAQCA8719H1ZC"
        posting_date = str(getdate())

        result = get_b2cl_json(
            {
                "29-Karnataka": [
                    {
                        "invoice_number": "SINV-0001",
                        "posting_date": posting_date,
                        "invoice_value": 1000,
                        "taxable_value": 1000,
                        "rate": 18,
                        "cess_amount": 0,
                    },
                    {
                        "invoice_number": "SINV-0002",
                        "posting_date": posting_date,
                        "invoice_value": 2000,
                        "taxable_value": 2000,
                        "rate": 18,
                        "cess_amount": 0,
                    },
                ]
            },
            gstin,
        )

        self.assertEqual(result[0]["pos"], "29")
        self.assertEqual(len(result[0]["inv"]), 2)
        self.assertEqual(result[0]["inv"][0]["itms"][0]["num"], 1)
        self.assertEqual(result[0]["inv"][1]["itms"][0]["num"], 1)


class TestGSTR1B2CS(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.filters = {
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "from_date": str(getdate()),
            "to_date": str(getdate()),
        }

    def _run(self, type_of_business):
        return execute({**self.filters, "type_of_business": type_of_business})[1]

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_b2cs_overseas_intra_state_credit_note(self):
        # Foreign customer, but an intra-state supply delivered within India (Gujarat
        # shipping address WITHOUT a GSTIN). Place of supply -- not the customer's
        # "Overseas" master -- governs the table: domestic B2C intra-state => B2C Small,
        # NOT exports/CDNUR.
        si = create_sales_invoice(
            customer="_Test Foreign Customer-1",
            shipping_address_name="_Test Foreign Customer-1-Shipping-Unregistered",
            place_of_supply="24-Gujarat",
            is_in_state=True,
        )

        cn = make_sales_return(si.name).save()
        cn.submit()

        b2cs = self._run("B2C Small")
        cdnur = self._run("CDNR-UNREG")

        # The supply is classified B2C Small (Table 7) keyed on place of supply: a
        # 24-Gujarat @ 18% row exists. (The legacy report aggregates SI + CN into one
        # (rate, place_of_supply) row, so individual document numbers are not retained
        # here -- the netting is asserted in the Beta test, which keeps per-document rows.)
        self.assertTrue(
            any(row.get("place_of_supply") == "24-Gujarat" and row.get("rate") == 18.0 for row in b2cs),
            f"Expected a B2C Small row for 24-Gujarat @ 18%; got {b2cs}",
        )

        # Neither the invoice nor the credit note must leak into CDNUR (it is not an
        # export and the place of supply is intra-state).
        cdnur_docs = {row.get("invoice_number") for row in cdnur}
        self.assertNotIn(si.name, cdnur_docs)
        self.assertNotIn(cn.name, cdnur_docs)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_cdnur_credit_note_not_double_counted_in_b2cs(self):
        # Inter-state B2C (Unregistered) invoice ABOVE the B2CL threshold (> 1 lakh),
        # then a PARTIAL credit note whose own value is BELOW the threshold. The legacy
        # report uses the ORIGINAL invoice total (return_against_invoice_total) to decide
        # B2CL, so the CN belongs only in CDNUR (Table 9B), never B2C Small.
        si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            place_of_supply="27-Maharashtra",  # inter-state vs company GSTIN 24...
            is_out_state=True,
            qty=10,
            rate=20000,  # original invoice value 2,00,000 > 1,00,000
        )

        cn = make_sales_return(si.name)
        cn.items[0].qty = -1  # partial return: CN own value 20,000 < 1,00,000
        cn.save()
        cn.submit()

        b2cs = self._run("B2C Small")
        cdnur = self._run("CDNR-UNREG")

        # CN must appear in CDNUR
        self.assertIn(cn.name, {row.get("invoice_number") for row in cdnur})

        # CN must NOT also appear in B2C Small
        self.assertNotIn(cn.name, {row.get("invoice_number") for row in b2cs})


def create_test_items():
    """Create Sales Invoices for testing GSTR1 Document Issued Summary."""

    invoices_for_outward_supply = JSON_OUTPUT["doc_det"][0]["docs"]
    debit_notes = JSON_OUTPUT["doc_det"][1]["docs"]
    credit_notes = JSON_OUTPUT["doc_det"][2]["docs"]
    purchase_rcm = JSON_OUTPUT["doc_det"][3]["docs"]

    # Sales Invoices
    sales_invoices = create_sales_invoices(3)
    create_sales_invoices(1)[0].cancel()
    sales_invoice = create_sales_invoices(1, do_not_save=True, do_not_submit=True)[0].save()

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
    sales_invoice = create_sales_invoices(1, is_return=1, qty=-1, do_not_save=True, do_not_submit=True)[
        0
    ].save()

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
    sales_invoice = create_sales_invoices(
        1, do_not_submit=True, company_address="_Test Indian Registered Company-Billing"
    )[0]
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

    # Purchase Invoices (RCM)

    # Registered RCM
    create_purchase_invoices(5)

    # Unregistered RCM
    purchases = create_purchase_invoices(5, supplier="_Test Unregistered Supplier")
    purchase_rcm.append(
        {
            "num": 1,
            "to": purchases[-1].name,
            "from": purchases[0].name,
            "totnum": 5,
            "cancel": 0,
            "net_issue": 5,
        }
    )


def create_sales_invoices(count, **kwargs):
    """Create a list of sales invoices."""
    return [create_sales_invoice(**kwargs) for _ in range(count)]


def create_purchase_invoices(count, **kwargs):
    """Create a list of purchase invoices."""
    return [create_purchase_invoice(**kwargs, is_reverse_charge=True) for _ in range(count)]


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
