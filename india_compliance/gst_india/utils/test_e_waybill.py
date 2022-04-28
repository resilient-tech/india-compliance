import unittest

from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import (
    create_sales_invoice,
)

from india_compliance.gst_india.utils.e_waybill import generate_e_waybill


class TestEWaybill(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.sales_invoice = create_sales_invoice(naming_series="SINV-.CFY.-")

    @classmethod
    def tearDownClass(self):
        self.sales_invoice.delete()

    def test_generate_e_waybill(self):
        doc = generate_e_waybill(self.sales_invoice.doctype, self.sales_invoice.name)
        print(doc)
