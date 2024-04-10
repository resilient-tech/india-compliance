# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

from enum import Enum

import frappe
from frappe.model.document import Document

from india_compliance.gst_india.utils.gstr.gstr_1 import GSTR1Invoices

# from frappe.utils import get_last_day, getdate


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
    B2B_REGULAR = "B2B Regular"  # Regular B2B
    B2B_REVERSE_CHARGE = "B2B Reverse Charge"  # Regular B2B
    SEZWP = "SEZWP"  # SEZ supplies with payment
    SEZWOP = "SEZWOP"  # SEZ supplies without payment
    DE = "Deemed Exports"  # Deemed Exp
    B2CL = "B2C (Large)"  # NA
    EXPWP = "EXPWP"  # WPAY
    EXPWOP = "EXPWOP"  # WOPAY
    B2CS = "B2C (Others)"  # NA
    NIL_RATED = "Nil-Rated"  # Inter vs Intra & Regis vs UnRegis
    EXEMPTED = "Exempted"  # Inter vs Intra & Regis vs UnRegis
    NON_GST = "Non-GST"  # Inter vs Intra & Regis vs UnRegis
    CDNR = "Credit/Debit Notes (Registered)"  # Like B2B
    CDNUR = "Credit/Debit Notes (Unregistered)"  # B2CL vs EXPWP vs EXPWOP
    # Other Sub-Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"  # UOM as per GOvt
    DOC_ISSUE = "Document Issued"


class DataFields(Enum):
    TRANSACTION_TYPE = "transaction_type"
    CUST_GSTIN = "customer_gstin"
    CUST_NAME = "customer_name"
    DOC_DATE = "document_date"
    DOC_NUMBER = "document_number"
    DOC_TYPE = "document_type"
    DOC_VALUE = "document_value"
    POS = "place_of_supply"
    REVERSE_CHARGE = "reverse_charge"
    TAXABLE_VALUE = "total_taxable_value"
    IGST = "total_igst_amount"
    CGST = "total_cgst_amount"
    SGST = "total_sgst_amount"
    CESS = "total_cess_amount"

    SHIPPING_BILL_NUMBER = "shipping_bill_number"
    SHIPPING_BILL_DATE = "shipping_bill_date"
    SHIPPING_PORT_CODE = "shipping_port_code"

    HSN_CODE = "hsn_code"
    DESCRIPTION = "description"
    UOM = "uom"
    TOTAL_QUANTITY = "total_quantity"

    FROM_SR = "from_sr_no"
    TO_SR = "to_sr_no"
    TOTAL_COUNT = "total_count"
    DRAFT_COUNT = "draft_count"
    CANCELLED_COUNT = "cancelled_count"


DATA = {
    "status": "Filed",
    "reconcile": {},
    "filed": {
        GSTR1_SubCategories.NIL_RATED.value: [
            {
                "document_category": "Inter-State supplies to registered persons",
                "taxable_value": 2000,
                "igst_amount": 0,
            },
        ],
        GSTR1_SubCategories.B2CS.value: [
            {
                "document_category": "OE",
                "place_of_supply": "01-JHARKHAND",
                "taxable_value": 2000,
                "igst_amount": 0,
                "tax_rate": 12,
                "cess_amount": 0,
                "e_commerce_gstin": "01AAACE9602H1Z5",
            },
            {
                "document_category": "OE",
                "place_of_supply": "01-JHARKHAND",
                "taxable_value": 2000,
                "igst_amount": 0,
                "tax_rate": 18,
                "cess_amount": 0,
                "e_commerce_gstin": "01AAACE9602H1Z5",
            },
        ],
    },
    "books": {
        GSTR1_SubCategories.B2B_REGULAR.value: [
            {
                "document_type": "Invoice",
                "customer_gstin": "29AABCE9602H1Z5",
                "customer_name": "ELECTROSTEEL CASTINGS LTD",
                "invoice_number": "INV-001",
                "document_date": "2024-04-01",
                "invoice_value": 1280,
                "place_of_supply": "01-JHARKHAND",
                "reverse_charge": "Y",
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
                    },
                    {
                        "idx": 1,
                        "tax_rate": 10,
                        "taxable_value": 2000,
                        "igst_amount": 200,
                        "cess_amount": 50,
                    },
                ],
            },
            {
                "document_type": "Invoice",
                "customer_gstin": "29AABCE9602H1Z5",
                "customer_name": "ELECTROSTEEL CASTINGS LTD",
                "invoice_number": "INV-002",
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_date": "2024-04-01",
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
                "document_category": "",
                "customer_name": "ELECTROSTEEL CASTINGS LTD",
                "document_number": "INV-014",
                "document_date": "2024-04-01",
                "document_value": 1280,
                "place_of_supply": "01-JHARKHAND",
                "is_reverse_charge": 0,
                "e_commerce_gstin": "01AAACE9602H1Z5",
                # "shipping_bill_number": "123456",
                # "shipping_bill_date": "2021-01-05",
                # "shipping_port_code": "INMAA1",
                "diff_percentage": 0,
                "taxable_value": 1000,
                "igst_amount": 0,
                "cess_amount": 0,
                "cgst_amount": 0,
                "sgst_amount": 0,
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
        GSTR1_SubCategories.NIL_RATED.value: [
            {
                "document_category": "Inter-State supplies to registered persons",
                "taxable_value": 1000,
                "document_number": "INV-015",
                "document_date": "2024-04-01",
                "igst_amount": 0,
            },
            {
                "document_category": "Inter-State supplies to registered persons",
                "taxable_value": 1000,
                "document_number": "INV-015",
                "document_date": "2024-04-01",
                "igst_amount": 0,
            },
        ],
        GSTR1_SubCategories.B2CS.value: [
            {
                "document_category": "OE",
                "place_of_supply": "01-JHARKHAND",
                "taxable_value": 1000,
                "igst_amount": 0,
                "tax_rate": 6,
                "cess_amount": 0,
                "e_commerce_gstin": "01AAACE9602H1Z5",
            },
            {
                "document_category": "OE",
                "place_of_supply": "01-JHARKHAND",
                "taxable_value": 1000,
                "igst_amount": 0,
                "tax_rate": 6,
                "cess_amount": 0,
                "e_commerce_gstin": "01AAACE9602H1Z5",
            },
        ],
    },
}


class GSTR1Beta(Document):
    def onload(self):
        # TODO: enqueue settings and handle enqueue
        data = getattr(self, "data", None)
        if data is not None:
            self.set_onload("data", data)

    def validate(self):
        # from_date = getdate(f"1-{self.month}-{self.year}")
        # to_date = get_last_day(from_date)
        # filters = {
        #     "company": self.company,
        #     "company_gstin": self.company_gstin,
        #     "from_date": from_date,
        #     "to_date": to_date,
        # }
        self.data = DATA


####################################################################################################
####### DOWNLOAD APIs ##############################################################################
####################################################################################################


@frappe.whitelist()
def download_books_as_excel(data):
    return "Data Downloaded to Excel Successfully"


@frappe.whitelist()
def download_reconcile_as_excel(data):
    return "Data Downloaded to Excel Successfully"


#################################
##### Process Data #############
################################
class GSTR1ProcessData:
    def process_data_for_invoice_no_key(self, invoice, prepared_data):
        invoice_sub_category = invoice.invoice_sub_category
        invoice_no = invoice.invoice_no

        mapped_dict = prepared_data.setdefault(invoice_sub_category, {}).setdefault(
            invoice_no,
            {
                DataFields.TRANSACTION_TYPE.value: "Invoice",
                DataFields.CUST_GSTIN.value: invoice.billing_address_gstin,
                DataFields.CUST_NAME.value: invoice.customer_name,
                DataFields.DOC_DATE.value: invoice.posting_date,
                DataFields.DOC_VALUE.value: invoice.invoice_total,
                DataFields.POS.value: invoice.place_of_supply,
                DataFields.REVERSE_CHARGE.value: invoice.is_reverse_charge,
                DataFields.DOC_TYPE.value: invoice.invoice_category,
                DataFields.TAXABLE_VALUE.value: 0,
                DataFields.IGST.value: 0,
                DataFields.CGST.value: 0,
                DataFields.SGST.value: 0,
                DataFields.CESS.value: 0,
                "diff_percentage": 0,
                "items": [],
            },
        )

        idx = len(mapped_dict["items"]) + 1

        mapped_dict["items"].append(
            {
                "idx": idx,
                "taxable_value": invoice.taxable_value,
                "igst_amount": invoice.igst_amount,
                "cgst_amount": invoice.cgst_amount,
                "sgst_amount": invoice.sgst_amount,
                "cess_amount": invoice.total_cess_amount,
            }
        )

        mapped_dict[DataFields.TAXABLE_VALUE.value] += invoice.taxable_value
        mapped_dict[DataFields.IGST.value] += invoice.igst_amount
        mapped_dict[DataFields.CGST.value] += invoice.cgst_amount
        mapped_dict[DataFields.SGST.value] += invoice.sgst_amount
        mapped_dict[DataFields.CESS.value] += invoice.total_cess_amount

    def process_data_for_document_category_key(self, invoice, prepared_data):
        key = invoice.invoice_type
        mapped_dict = prepared_data.setdefault(key, [])

        for row in mapped_dict:
            if row[DataFields.DOC_NUMBER.value] == invoice.invoice_no:
                row[DataFields.TAXABLE_VALUE.value] += invoice.taxable_value
                row[DataFields.IGST.value] += invoice.igst_amount
                row[DataFields.CGST.value] += invoice.cgst_amount
                row[DataFields.SGST.value] += invoice.sgst_amount
                row[DataFields.CESS.value] += invoice.total_cess_amount
                return

        mapped_dict.append(
            {
                DataFields.TAXABLE_VALUE.value: invoice.taxable_value,
                DataFields.DOC_NUMBER.value: invoice.invoice_no,
                DataFields.DOC_DATE.value: invoice.posting_date,
                DataFields.IGST.value: invoice.igst_amount,
                DataFields.CGST.value: invoice.cgst_amount,
                DataFields.SGST.value: invoice.sgst_amount,
                DataFields.CESS.value: invoice.total_cess_amount,
            }
        )

    def process_data_for_b2cs(self, invoice, prepared_data):
        key = (invoice.place_of_supply, invoice.gst_rate, invoice.e_commerce_gstin)
        mapped_dict = prepared_data.setdefault("B2C (Others)", {})
        invoices_list = mapped_dict.setdefault(key, [])

        for row in invoices_list:
            if row[DataFields.DOC_NUMBER.value] == invoice.invoice_no:
                row[DataFields.TAXABLE_VALUE.value] += invoice.taxable_value
                row[DataFields.IGST.value] += invoice.igst_amount
                row[DataFields.CGST.value] += invoice.cgst_amount
                row[DataFields.SGST.value] += invoice.sgst_amount
                row[DataFields.CESS.value] += invoice.total_cess_amount
                return

        invoices_list.append(
            {
                DataFields.DOC_NUMBER.value: invoice.invoice_no,
                DataFields.POS.value: invoice.place_of_supply,
                DataFields.TAXABLE_VALUE.value: invoice.taxable_value,
                "tax_rate": invoice.gst_rate,
                DataFields.IGST.value: invoice.igst_amount,
                DataFields.CGST.value: invoice.cgst_amount,
                DataFields.SGST.value: invoice.sgst_amount,
                DataFields.CESS.value: invoice.total_cess_amount,
                "e_commerce_gstin": invoice.e_commerce_gstin,
            }
        )


class GSTR1MappedData(GSTR1ProcessData):
    def prepare_mapped_data(self, filters):
        _class = GSTR1Invoices(filters)
        data = _class.get_invoices_for_item_wise_summary()
        _class.process_invoices(data)
        prepared_data = {}

        for invoice in data:

            if invoice["invoice_category"] in (
                "B2B,SEZ,DE",
                "B2C (Large)",
                "CDNR",
                "CDNUR",
                "Exports",
            ):
                self.process_data_for_invoice_no_key(invoice, prepared_data)
            elif invoice["invoice_category"] == "Nil-Rated, Exempted, Non-GST":
                self.process_data_for_document_category_key(invoice, prepared_data)
            elif invoice["invoice_category"] == "B2C (Others)":
                self.process_data_for_b2cs(invoice, prepared_data)

        return prepared_data
