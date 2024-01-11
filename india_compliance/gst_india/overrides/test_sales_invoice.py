import unittest

import frappe

from india_compliance.gst_india.utils import validate_invoice_number


class TestSalesInvoice(unittest.TestCase):
    def test_validate_invoice_number(self):
        posting_date = "2021-05-01"

        invalid_names = [
            "SI$1231",
            "012345678901234567",
            "SI 2020 05",
            "SI.2020.0001",
            "PI2021 - 001",
        ]
        for name in invalid_names:
            doc = frappe._dict(name=name, posting_date=posting_date)
            self.assertRaises(frappe.ValidationError, validate_invoice_number, doc)

        valid_names = [
            "012345678901236",
            "SI/2020/0001",
            "SI/2020-0001",
            "2020-PI-0001",
            "PI2020-0001",
        ]
        for name in valid_names:
            doc = frappe._dict(name=name, posting_date=posting_date)
            try:
                validate_invoice_number(doc)
            except frappe.ValidationError:
                self.fail("Valid name {} throwing error".format(name))
