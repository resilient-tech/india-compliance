import unittest

import frappe

from india_compliance.gst_india.utils import read_json_data_file
from india_compliance.gst_india.utils.gstr import ReturnType, save_gstr


class TestGSTRMixin:
    def get_inward_supply(self, category):
        docname = frappe.get_value(
            self.doctype,
            {"company_gstin": self.gstin, "classification": category.value},
            "*",
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


class TestGSTR2a(unittest.TestCase, TestGSTRMixin):
    # TODO: make tests for individual categories
    @classmethod
    def setUpClass(cls):
        cls.gstin = "01AABCE2207R1Z5"
        cls.return_period = "032020"
        cls.doctype = "Inward Supply"

        save_gstr(
            cls.gstin,
            ReturnType.GSTR2A,
            cls.return_period,
            read_json_data_file("test_gstr_2a"),
        )

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete("Inward Supply", {"company_gstin": cls.gstin})

    def test_gstr2a_b2b(self):
        pass

    def test_gstr2a_b2ba(self):
        #  TODO: implement test
        pass

    def test_gstr2a_cdnr(self):
        #  TODO: implement test
        pass

    def test_gstr2a_cdnra(self):
        # TODO: values?
        pass

    def test_gstr2a_isd(self):
        # TODO: values?
        pass

    def test_gstr2a_isda(self):
        #  TODO: implement test
        pass

    def test_gstr2a_impg(self):
        #  TODO: implement test
        pass

    def test_gstr2a_impgsez(self):
        #  TODO: implement test
        pass
