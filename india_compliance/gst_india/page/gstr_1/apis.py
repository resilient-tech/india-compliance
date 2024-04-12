import random

import frappe

GSTR1_ACTIONS = {
    "B2B": "B2B",
    "AT": "AT",
    "B2CL": "B2CL",
    "B2CS": "B2CS",
    "CDNR": "CDNR",
    "CDNUR": "CDNUR",
    "DOCISS": "DOC_ISSUE",
    "EXP": "EXP",
    "RETSUM": "SEC_SUM",
    "HSNSUM": "HSN",
    "NIL": "NIL",
    "TXP": "TXP",
}


@frappe.whitelist()
def get_mock_data():
    return {
        key.lower(): (
            [
                {
                    "document_type": "Invoice",
                    "customer_gstin": "29AABCE9602H1Z5",
                    "customer_name": "ELECTROSTEEL CASTINGS LTD",
                    "invoice_number": f"INV-00{i+1}",
                    "invoice_date": "2021-01-05",
                    "invoice_value": i * 1000,
                    "place_of_supply": "01-JHARKHAND",
                    "reverse_charge": "N",
                    "e_commerce_gstin": "01AAACE9602H1Z5",
                    "invoice_category": "B2B",
                    "invoice_sub_category": "Regular",
                    "shipping_bill_number": "123456",
                    "shipping_bill_date": "2021-01-05",
                    "shipping_port_code": "INMAA1",
                    "diff_percentage": 0,
                    "items": [
                        {
                            "idx": 1,
                            "tax_rate": 18,
                            "taxable_value": i * 1000,
                            "igst_amount": (i * 180) if i % 2 == 0 else 0,
                            "sgst_amount": (i * 90) if i % 2 == 1 else 0,
                            "cgst_amount": (i * 90) if i % 2 == 1 else 0,
                            "cess_amount": 0,
                        }
                    ],
                }
                for i in range(1, random.randint(8, 12))
            ]
            if key not in ["AT", "B2CL", "EXP", "RETSUM"]
            else []
        )
        for key in GSTR1_ACTIONS.keys()
    }
