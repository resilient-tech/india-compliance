# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
import re

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from india_compliance.gst_india.doctype.gst_hsn_code.gst_hsn_code import (
    update_taxes_in_item_master,
)
from india_compliance.gst_india.utils import get_hsn_code_list

<<<<<<< HEAD
=======
IGNORE_TEST_RECORD_DEPENDENCIES = ["Item Tax Template", "Tax Category"]

FOUR_DIGIT_HSN = "0101"
SIX_DIGIT_HSN = "010121"
EIGHT_DIGIT_HSN = "01012100"


class TestGSTHSNCode(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
>>>>>>> b296625a (fix: convert hsn field in transactions as autocomplete fields)

class TestGSTHSNCode(FrappeTestCase):
    @change_settings("GST Settings", {"validate_hsn_code": 0})
    def test_validate_hsn_when_validate_hsn_code_disabled(self):
        doc = frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "1"})
        doc.save()
        self.assertDocumentEqual({"hsn_code": 1}, frappe.get_doc("GST HSN Code", "1"))

    def test_validate_hsn_with_invalid_hsn_length(self):
        doc = frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "100"})
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(HSN/SAC Code should be .*)"),
            doc.save,
        )

    @change_settings("GST Settings", {"validate_hsn_code": 1, "min_hsn_digits": 8})
    def test_validate_hsn_with_8_digit_setting(self):
        doc = frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "100000"})
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(HSN/SAC Code should be .*)"),
            doc.save,
        )

        doc = frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "10000000"})
        doc.save()

    @change_settings("GST Settings", {"validate_hsn_code": 1, "min_hsn_digits": 6})
    def test_get_hsn_code_list_by_description(self):
        # codes whose description matches, but which the code prefix search would miss
        options = get_hsn_code_list(txt="HORSES FOR POLO", limit=100)
        self.assertEqual([option.value for option in options], ["01012910", "01019010"])

        # LIKE is case insensitive on MariaDB, and rendered as ILIKE on Postgres
        self.assertEqual(options, get_hsn_code_list(txt="horses for polo", limit=100))

    @change_settings("GST Settings", {"validate_hsn_code": 1, "min_hsn_digits": 8})
    def test_get_hsn_code_list_respects_min_hsn_digits(self):
        options = get_hsn_code_list(txt=FOUR_DIGIT_HSN, limit="100")
        codes = [option.value for option in options]

        self.assertIn(EIGHT_DIGIT_HSN, codes)
        self.assertNotIn(FOUR_DIGIT_HSN, codes)
        self.assertNotIn(SIX_DIGIT_HSN, codes)

        option = options[0]
        self.assertEqual(option.label, option.value)
        self.assertEqual(
            option.description,
            frappe.db.get_value("GST HSN Code", option.value, "description"),
        )

    def test_update_taxes_in_item_master(self):
        taxes = [{"item_tax_template": "GST 12% - _TIUC", "tax_category": "In-State"}]
        doc = frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "100000", "taxes": taxes})
        doc.save()
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": "SKU9999",
                "item_group": "All Item Groups",
                "gst_hsn_code": "100000",
                "stock_uom": "Nos",
            }
        )
        item.save()
        update_taxes_in_item_master(taxes=taxes, hsn_code="100000")
        self.assertDocumentEqual(taxes[0], frappe.get_doc("Item", "SKU9999").taxes[0])
