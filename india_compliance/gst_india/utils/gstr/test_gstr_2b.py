from datetime import date

import frappe
from frappe import parse_json, read_file
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr import GSTRCategory, save_gstr_2b
from india_compliance.gst_india.utils.gstr.test_gstr_2a import TestGSTRMixin


class TestGSTR2b(FrappeTestCase, TestGSTRMixin):
    @classmethod
    def setUpClass(cls):
        cls.gstin = "01AABCE2207R1Z5"
        cls.return_period = "032020"
        cls.doctype = "GST Inward Supply"
        cls.log_doctype = "GSTR Import Log"
        cls.test_data = parse_json(read_file(get_data_file_path("test_gstr_2b.json")))

        save_gstr_2b(
            cls.gstin,
            cls.return_period,
            cls.test_data,
        )

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete(cls.doctype, {"company_gstin": cls.gstin})
        frappe.db.delete(cls.log_doctype, {"gstin": cls.gstin})

    def test_gstr2b_b2b(self):
        doc = self.get_doc(GSTRCategory.B2B)
        self.assertImportLog()
        self.assertDocumentEqual(
            {
                "company_gstin": "01AABCE2207R1Z5",
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "supplier_gstin": "01AABCE2207R1Z5",
                "supplier_name": "GSTN",
                "gstr_1_filing_date": date(2019, 11, 18),
                "sup_return_period": "112019",
                "bill_no": "S008400",
                "supply_type": "Regular",
                "bill_date": date(2016, 11, 24),
                "document_value": 729248.16,
                "place_of_supply": "06-Haryana",
                "is_reverse_charge": 0,
                "itc_availability": "No",
                "reason_itc_unavailability": (
                    "POS and supplier state are same but recipient state is different"
                ),
                "diffprcnt": "1",
                "irn_source": "e-Invoice",
                "irn_number": (
                    "897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"
                ),
                "irn_gen_date": date(2019, 12, 24),
                "doc_type": "Invoice",
                "items": [
                    {
                        "item_number": 1,
                        "rate": 5,
                        "taxable_value": 400,
                        "igst": 0,
                        "cgst": 200,
                        "sgst": 200,
                        "cess": 0,
                    }
                ],
            },
            doc,
        )

    def test_gstr2b_b2ba(self):
        doc = self.get_doc(GSTRCategory.B2BA)
        self.assertDocumentEqual(
            {
                "company_gstin": "01AABCE2207R1Z5",
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "supplier_gstin": "01AABCE2207R1Z5",
                "supplier_name": "GSTN",
                "gstr_1_filing_date": date(2019, 11, 18),
                "sup_return_period": "112019",
                "bill_no": "S008400",
                "supply_type": "Regular",
                "bill_date": date(2016, 11, 24),
                "document_value": 729248.16,
                "place_of_supply": "06-Haryana",
                "is_reverse_charge": 0,
                "itc_availability": "No",
                "reason_itc_unavailability": (
                    "POS and supplier state are same but recipient state is different"
                ),
                "diffprcnt": "1",
                "original_bill_no": "S008400",
                "original_bill_date": date(2016, 11, 24),
                "doc_type": "Invoice",
                "items": [
                    {
                        "item_number": 1,
                        "rate": 5,
                        "taxable_value": 400,
                        "igst": 0,
                        "cgst": 200,
                        "sgst": 200,
                        "cess": 0,
                    }
                ],
            },
            doc,
        )

    def test_gstr2b_cdnr(self):
        doc = self.get_doc(GSTRCategory.CDNR)
        self.assertDocumentEqual(
            {
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "supplier_gstin": "01AAAAP1208Q1ZS",
                "supplier_name": "GSTN",
                "gstr_1_filing_date": date(2019, 11, 18),
                "sup_return_period": "112019",
                "bill_no": "533515",
                "supply_type": "Regular",
                "bill_date": date(2016, 9, 23),
                "document_value": 729248.16,
                "place_of_supply": "01-Jammu and Kashmir",
                "is_reverse_charge": 0,
                "itc_availability": "No",
                "reason_itc_unavailability": "Return filed post annual cut-off",
                "diffprcnt": "1",
                "irn_source": "e-Invoice",
                "irn_number": (
                    "897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"
                ),
                "irn_gen_date": date(2019, 12, 24),
                "doc_type": "Credit Note",
                "items": [
                    {
                        "item_number": 1,
                        "rate": 5,
                        "taxable_value": 400,
                        "igst": 400,
                        "cgst": 0,
                        "sgst": 0,
                        "cess": 0,
                    }
                ],
            },
            doc,
        )

    def test_gstr2b_cdnra(self):
        doc = self.get_doc(GSTRCategory.CDNRA)
        self.assertDocumentEqual(
            {
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "supplier_gstin": "01AAAAP1208Q1ZS",
                "supplier_name": "GSTN",
                "gstr_1_filing_date": date(2019, 11, 18),
                "sup_return_period": "112019",
                "original_bill_no": "533515",
                "original_bill_date": date(2016, 9, 23),
                "original_doc_type": "Credit Note",
                "bill_no": "533515",
                "supply_type": "Regular",
                "bill_date": date(2016, 9, 23),
                "document_value": 729248.16,
                "place_of_supply": "01-Jammu and Kashmir",
                "is_reverse_charge": 0,
                "itc_availability": "No",
                "reason_itc_unavailability": "Return filed post annual cut-off",
                "diffprcnt": "1",
                "doc_type": "Credit Note",
                "items": [
                    {
                        "item_number": 1,
                        "rate": 5,
                        "taxable_value": 400,
                        "igst": 0,
                        "cgst": 200,
                        "sgst": 200,
                        "cess": 0,
                    }
                ],
            },
            doc,
        )

    def test_gstr2b_isd(self):
        doc = self.get_doc(GSTRCategory.ISD)
        self.assertDocumentEqual(
            {
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "gstr_1_filing_date": date(2020, 3, 2),
                "sup_return_period": "022020",
                "supplier_gstin": "16DEFPS8555D1Z7",
                "supplier_name": "GSTN",
                "doc_type": "ISD Invoice",
                "bill_no": "S0080",
                "bill_date": date(2016, 3, 3),
                "itc_availability": "Yes",
                "document_value": 400,
                "items": [
                    {
                        "igst": 0,
                        "cgst": 200,
                        "sgst": 200,
                        "cess": 0,
                    }
                ],
            },
            doc,
        )

    def test_gstr2b_isda(self):
        doc = self.get_doc(GSTRCategory.ISDA)
        self.assertDocumentEqual(
            {
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "gstr_1_filing_date": date(2020, 3, 2),
                "sup_return_period": "022020",
                "supplier_gstin": "16DEFPS8555D1Z7",
                "supplier_name": "GSTN",
                "original_doc_type": "ISD Credit Note",
                "original_bill_no": "1004",
                "original_bill_date": date(2016, 3, 2),
                "doc_type": "ISD Invoice",
                "bill_no": "S0080",
                "bill_date": date(2016, 3, 3),
                "itc_availability": "Yes",
                "document_value": 400,
                "items": [
                    {
                        "igst": 0,
                        "cgst": 200,
                        "sgst": 200,
                        "cess": 0,
                    }
                ],
            },
            doc,
        )

    def test_gstr2b_impg(self):
        doc = self.get_doc(GSTRCategory.IMPG)
        self.assertDocumentEqual(
            {
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "doc_type": "Bill of Entry",
                "port_code": "18272A",
                "bill_no": "2566282",
                "bill_date": date(2019, 11, 18),
                "is_amended": 0,
                "document_value": 246.54,
                "items": [
                    {
                        "taxable_value": 123.02,
                        "igst": 123.02,
                        "cess": 0.5,
                    }
                ],
            },
            doc,
        )

    def test_gstr2b_impgsez(self):
        doc = self.get_doc(GSTRCategory.IMPGSEZ)
        self.assertDocumentEqual(
            {
                "return_period_2b": "032020",
                "gen_date_2b": date(2020, 4, 14),
                "supplier_gstin": "01AABCE2207R1Z5",
                "supplier_name": "GSTN",
                "doc_type": "Bill of Entry",
                "port_code": "18272A",
                "bill_no": "2566282",
                "bill_date": date(2019, 11, 18),
                "is_amended": 0,
                "document_value": 246.54,
                "items": [
                    {
                        "taxable_value": 123.02,
                        "igst": 123.02,
                        "cess": 0.5,
                    }
                ],
            },
            doc,
        )
