import unittest

import frappe

from india_compliance.gst_india.utils import parse_datetime, read_json_data_file
from india_compliance.gst_india.utils.gstr import GSTRCategory, ReturnType, save_gstr
from india_compliance.gst_india.utils.gstr.test_gstr_2a import TestGSTRMixin


class TestGSTR2b(unittest.TestCase, TestGSTRMixin):
    @classmethod
    def setUpClass(cls):
        cls.gstin = "01AABCE2207R1Z5"
        cls.return_period = "032020"
        cls.doctype = "Inward Supply"

        save_gstr(
            cls.gstin,
            ReturnType.GSTR2B,
            cls.return_period,
            read_json_data_file("test_gstr_2b").get("data", {}).get("docdata"),
        )

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete("Inward Supply", {"company_gstin": cls.gstin})

    def test_gstr2b_b2b(self):
        expected_values = {
            "company_gstin": "01AABCE2207R1Z5",
            "return_period_2b": "032020",
            # TODO: uncomment this after solving the issue
            # "gen_date_2b": parse_datetime("14-04-2020", day_first=True).date(),
            "supplier_gstin": "01AABCE2207R1Z5",
            "supplier_name": "GSTN",
            "gstr_1_filing_date": parse_datetime("18-11-2019", day_first=True).date(),
            "sup_return_period": "112019",
            "doc_number": "S008400",
            "supply_type": "Regular",
            "doc_date": parse_datetime("24-11-2016", day_first=True).date(),
            "document_value": 729248.16,
            "place_of_supply": "06-Haryana",
            "reverse_charge": 0,
            "itc_availability": "No",
            "reason_itc_unavailability": (
                "POS and supplier state are same but recipient state is different"
            ),
            "diffprcnt": "1",
            "irn_source": "e-Invoice",
            "irn_number": (
                "897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"
            ),
            "irn_gen_date": parse_datetime("24-12-2019", day_first=True).date(),
            "doc_type": "Invoice",
            # TODO: why these fields are here - aren't they only for 2A?
            # "other_return_period": "122018",
            # "amendment_type": "Receiver GSTIN Amended",
            # "gstr_3b_filled": 1,
        }

        expected_item = {
            "item_number": 1,
            "rate": 5,
            "taxable_value": 400,
            "igst": 0,
            "cgst": 200,
            "sgst": 200,
            "cess": 0,
        }

        self.assertInwardSupply(
            self.get_inward_supply(GSTRCategory.B2B),
            expected_values,
            expected_item,
        )

    def test_gstr2b_b2ba(self):
        #  TODO: implement test
        pass

    def test_gstr2b_cdnr(self):
        #  TODO: implement test
        pass

    def test_gstr2b_cdnra(self):
        #  TODO: implement test
        pass

    def test_gstr2b_isd(self):
        #  TODO: implement test
        pass

    def test_gstr2b_isda(self):
        expected_values = {
            "gstr_1_filing_date": parse_datetime("02-03-2020", day_first=True).date(),
            "sup_return_period": "022020",
            "supplier_gstin": "16DEFPS8555D1Z7",
            "supplier_name": "GSTN",
            "original_doc_type": "ISD Credit Note",
            "original_doc_number": "1004",
            "original_doc_date": parse_datetime("02-03-2016", day_first=True).date(),
            "doc_type": "ISD Invoice",
            "doc_number": "S0080",
            "doc_date": parse_datetime("03-03-2016", day_first=True).date(),
            "itc_availability": "Yes",
        }

        expected_item = {
            "igst": 0,
            "cgst": 200,
            "sgst": 200,
            "cess": 0,
        }

        self.assertInwardSupply(
            self.get_inward_supply(GSTRCategory.ISDA),
            expected_values,
            expected_item,
        )

    def test_gstr2b_impg(self):
        expected_values = {
            "doc_type": "Bill of Entry",
            "port_code": "18272A",
            "doc_number": "2566282",
            "doc_date": parse_datetime("18-11-2019", day_first=True).date(),
            "is_amended": 0,
        }
        expected_item = {
            "taxable_value": 123.02,
            "igst": 123.02,
            "cess": 0.5,
        }

        self.assertInwardSupply(
            self.get_inward_supply(GSTRCategory.IMPG),
            expected_values,
            expected_item,
        )

    def test_gstr2a_impgsez(self):
        expected_values = {
            "supplier_gstin": "01AABCE2207R1Z5",
            "supplier_name": "GSTN",
            "doc_type": "Bill of Entry",
            "port_code": "18272A",
            "doc_number": "2566282",
            "doc_date": parse_datetime("18-11-2019").date(),
            "is_amended": 0,
        }
        expected_item = {
            "taxable_value": 123.02,
            "igst": 123.02,
            "cess": 0.5,
        }

        self.assertInwardSupply(
            self.get_inward_supply(GSTRCategory.IMPGSEZ),
            expected_values,
            expected_item,
        )
