# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from enum import Enum

from frappe.model.document import Document

DATA = {
    "status": "Not Filed",
    "filed": [],
    "books": [
        {
            "document_type": "Invoice",
            "customer_gstin": "29AABCE9602H1Z5",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-001",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2B, SEZ, DE",
            "invoice_sub_category": "B2B Regular",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_gstin": "29AABCE9602H1Z5",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-002",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2B, SEZ, DE",
            "invoice_sub_category": "B2B Reverse Charge",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_gstin": "29AABCE9602H1Z5",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-003",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2B, SEZ, DE",
            "invoice_sub_category": "SEZWP",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_gstin": "29AABCE9602H1Z5",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-004",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2B, SEZ, DE",
            "invoice_sub_category": "SEZWOP",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-005",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2B, SEZ, DE",
            "invoice_sub_category": "Deemed Exports",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-006",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2C (Large)",
            "invoice_sub_category": "B2C (Large)",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-007",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2C (Large)",
            "invoice_sub_category": "B2C (Large)",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-008",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2C (Large)",
            "invoice_sub_category": "B2C (Large)",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 18,
                    "taxable_value": 1000,
                    "igst_amount": 180,
                    "cess_amount": 100,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-009",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "B2C (Others)",
            "invoice_sub_category": "B2C (Others)",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 0,
                    "taxable_value": 1000,
                    "igst_amount": 0,
                    "cess_amount": 0,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-010",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "Nil-Rated, Exempted, Non-GST",
            "invoice_sub_category": "Nil-Rated",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 0,
                    "taxable_value": 1000,
                    "igst_amount": 0,
                    "cess_amount": 0,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-011",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "Nil-Rated, Exempted, Non-GST",
            "invoice_sub_category": "Exempted",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 0,
                    "taxable_value": 1000,
                    "igst_amount": 0,
                    "cess_amount": 0,
                }
            ],
        },
        {
            "document_type": "Invoice",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-012",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "Nil-Rated, Exempted, Non-GST",
            "invoice_sub_category": "Non-GST",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 0,
                    "taxable_value": 1000,
                    "igst_amount": 0,
                    "cess_amount": 0,
                }
            ],
        },
        {
            "document_type": "Credit Note",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-013",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "Credit/Debit Notes (Registered)",
            "invoice_sub_category": "Credit/Debit Notes (Registered)",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 0,
                    "taxable_value": 1000,
                    "igst_amount": 0,
                    "cess_amount": 0,
                }
            ],
        },
        {
            "document_type": "Credit Note",
            "customer_name": "ELECTROSTEEL CASTINGS LTD",
            "invoice_number": "INV-014",
            "invoice_date": "2024-04-01",
            "invoice_value": 1280,
            "place_of_supply": "01-JHARKHAND",
            "is_reverse_charge": 0,
            "e_commerce_gstin": "01AAACE9602H1Z5",
            "invoice_category": "Credit/Debit Notes (Unregistered)",
            "invoice_sub_category": "Credit/Debit Notes (Unregistered)",
            # "shipping_bill_number": "123456",
            # "shipping_bill_date": "2021-01-05",
            # "shipping_port_code": "INMAA1",
            "diff_percentage": 0,
            "items": [
                {
                    "idx": 1,
                    "tax_rate": 0,
                    "taxable_value": 1000,
                    "igst_amount": 0,
                    "cess_amount": 0,
                }
            ],
        },
    ],
}


class GSTR1Beta(Document):
    def onload(self):
        # TODO: enqueue settings and handle enqueue
        data = getattr(self, "data", None)
        if data is not None:
            self.set_onload("data", data)

    def validate(self):
        self.data = DATA


class GSTR1_Categories(Enum):
    B2B = "B2B,SEZ,DE"
    B2CL = "B2C (Large)"
    EXP = "Exports"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"
    # Other Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    DOC_ISSUE = "Document Issued"
    HSN = "HSN Summary"


class GSTR1_SubCategories(Enum):
    B2B_REGULAR = "B2B Regular"
    B2B_REVERSE_CHARGE = "B2B Reverse Charge"
    SEZWP = "SEZWP"
    SEZWOP = "SEZWOP"
    DE = "Deemed Exports"
    B2CL = "B2C (Large)"
    EXPWP = "EXPWP"
    EXPWOP = "EXPWOP"
    B2CS = "B2C (Others)"
    NIL_RATED = "Nil-Rated"
    EXEMPTED = "Exempted"
    NON_GST = "Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"
    # Other Sub-Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"
    DOC_ISSUE = "Document Issued"


DATA = {GSTR1_SubCategories.B2B_REGULAR: []}
