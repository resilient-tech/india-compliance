import datetime
from unittest.mock import Mock, patch

import frappe
from frappe import parse_json, read_file
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr import save_gstr_2a


class TestGSTRMixin:
    def get_doc(self, category):
        docname = frappe.get_value(
            self.doctype,
            {"company_gstin": self.gstin, "classification": category.value},
        )
        self.assertIsNotNone(docname)
        return frappe.get_doc(self.doctype, docname)

    def assertInwardSupply(self, doc, expected_values, expected_item=None):
        for key, value in expected_values.items():
            print(key, value, doc.get(key))
            self.assertEqual(doc.get(key), value)

        if not expected_item:
            return

        items = doc.get("items")
        self.assertIsNotNone(items)
        self.assertEqual(len(items), 1)

        for key, value in expected_item.items():
            self.assertEqual(items[0].get(key), value)


class TestGSTR2a(FrappeTestCase, TestGSTRMixin):
    # Tests as per version 2.1 of GSTR2A Dt: 14-10-2020
    # TODO: make tests for individual categories
    @classmethod
    def setUpClass(cls):
        cls.gstin = "01AABCE2207R1Z5"
        cls.return_period = "032020"
        cls.doctype = "Inward Supply"

        save_gstr_2a(
            cls.gstin,
            cls.return_period,
            parse_json(read_file(get_data_file_path("test_gstr_2a.json"))),
        )

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete("Inward Supply", {"company_gstin": cls.gstin})

    def test_gstr2a_b2b(self):
        pass

    def test_gstr2a_b2ba(self):
        doc = frappe.get_doc()

    def test_gstr2a_cdn(self):
        doc = frappe.get_doc(
            self.doctype, {"company_gstin": self.gstin, "classification": "CDNR"}
        )
        self.assertTrue(doc)
        self.assertDocumentEqual(
            {
                "doc_date": datetime.date(2018, 9, 23),
                "doc_number": "533515",
                "doc_type": "Credit Note",
                "supplier_gstin": "01AAAAP1208Q1ZS",
                "supply_type": "Regular",
                "place_of_supply": "06-Haryana",
                "items": [
                    {
                        "item_number": 1,
                        "taxable_value": 6210.99,
                        "rate": 10.1,
                        "igst": 0,
                        "cgst": 614.44,
                        "sgst": 5.68,
                        "cess": 621.09,
                    }
                ],
                "document_value": 729248.16,
                "diffprcnt": "0.65",
                "other_return_period": "122018",
                "amendment_type": "Receiver GSTIN Amended",
                "sup_return_period": "042018",
                "gstr_1_filled": 1,
                "gstr_3b_filled": 1,
                "gstr_1_filing_date": datetime.date(2020, 5, 12),
                "registration_cancel_date": datetime.date(2019, 8, 27),
                "irn_source": "e-Invoice",
                "irn_number": (
                    "897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"
                ),
                "irn_gen_date": datetime.date(2019, 12, 24),
            },
            doc,
        )

    def test_gstr2a_cdna(self):
        doc = frappe.get_doc(
            self.doctype, {"company_gstin": self.gstin, "classification": "CDNRA"}
        )
        self.assertTrue(doc)
        self.assertDocumentEqual(
            {
                "doc_date": datetime.date(2018, 9, 23),
                "doc_number": "533515",
                "doc_type": "Credit Note",
                "supplier_gstin": "01AAAAP1208Q1ZS",
                "supply_type": "Regular",
                "place_of_supply": "01-Jammu and Kashmir",
                "items": [
                    {
                        "item_number": 1,
                        "taxable_value": 400,
                        "igst": 0,
                        "cgst": 200,
                        "sgst": 200,
                        "cess": 0,
                    }
                ],
                "document_value": 729248.16,
                "diffprcnt": "1",
                "other_return_period": "122018",
                "amendment_type": "Receiver GSTIN Amended",
                "original_doc_number": "533515",
                "original_doc_date": datetime.date(2016, 9, 23),
                "original_doc_type": "Credit Note",
                "sup_return_period": "112019",
                "gstr_1_filled": 1,
                "gstr_3b_filled": 1,
                "gstr_1_filing_date": datetime.date(2019, 11, 18),
                "registration_cancel_date": datetime.date(2019, 8, 27),
            },
            doc,
        )

    def test_gstr2a_isd(self):
        doc = frappe.get_doc(
            self.doctype, {"company_gstin": self.gstin, "classification": "ISD"}
        )
        self.assertTrue(doc)
        self.assertDocumentEqual(
            {
                "doc_date": datetime.date(2016, 3, 3),
                "doc_number": "S0080",
                "doc_type": "ISD Invoice",
                "supplier_gstin": "16DEFPS8555D1Z7",
                "itc_availability": "Yes",
                "other_return_period": "122018",
                "amendment_type": "Receiver GSTIN Amended",
                "is_amended": 1,
                "document_value": 80,
                "items": [
                    {
                        "igst": 20,
                        "cgst": 20,
                        "sgst": 20,
                        "cess": 20,
                    }
                ],
            },
            doc,
        )

    def test_gstr2a_isda(self):
        # No such API exists. Its merged with ISD.
        pass

    def test_gstr2a_impg(self):
        doc = frappe.get_doc(
            self.doctype, {"company_gstin": self.gstin, "classification": "IMPG"}
        )
        self.assertTrue(doc)
        self.assertDocumentEqual(
            {
                "doc_date": datetime.date(2019, 11, 18),
                "port_code": "18272A",
                "doc_number": "2566282",
                "doc_type": "Bill of Entry",
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

    def test_gstr2a_impgsez(self):
        doc = frappe.get_doc(
            self.doctype, {"company_gstin": self.gstin, "classification": "IMPGSEZ"}
        )
        self.assertTrue(doc)
        self.assertDocumentEqual(
            {
                "doc_date": datetime.date(2019, 11, 18),
                "port_code": "18272A",
                "doc_number": "2566282",
                "doc_type": "Bill of Entry",
                "supplier_gstin": self.gstin,
                "supplier_name": "GSTN",
                "is_amended": 0,
                "document_value": 246.54,
                "items": [
                    {
                        "taxable_value": 123.02,
                        "igst": 123.02,
                        "cgst": 0,
                        "sgst": 0,
                        "cess": 0.5,
                    }
                ],
            },
            doc,
        )
