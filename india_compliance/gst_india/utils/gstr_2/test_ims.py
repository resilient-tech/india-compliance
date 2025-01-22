from datetime import date

import frappe
from frappe import parse_json, read_file
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr_2 import save_ims_invoices


class TestIMS(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.gstin = "24AAQCA8719H1ZC"
        cls.doctype = "GST Inward Supply"
        cls.test_data = parse_json(read_file(get_data_file_path("test_ims.json")))

        save_ims_invoices(cls.gstin, "ALL", cls.test_data)

    def get_doc(self, category, doc_type):
        docname = frappe.get_value(
            self.doctype,
            {
                "company_gstin": self.gstin,
                "classification": category,
                "doc_type": doc_type,
            },
        )
        self.assertIsNotNone(docname)
        return frappe.get_doc(self.doctype, docname)

    def test_ims_b2b(self):
        doc = self.get_doc("B2B", "Invoice")
        print(doc.as_dict())
        self.assertDocumentEqual(
            {
                "bill_date": date(2023, 1, 23),
                "bill_no": "b1",
                "doc_type": "Invoice",
                "supplier_gstin": "24MAYAS0100J1JD",
                "supply_type": "Regular",
                "classification": "B2B",
                "place_of_supply": "24-Gujarat",
                "document_value": 1000,
                "is_downloaded_from_ims": 1,
                "ims_action": "Accepted",
                "previous_ims_action": "Accepted",
                "is_pending_action_allowed": 1,
                "is_supplier_return_filed": 0,
                "supplier_return_form": "R1",
                "sup_return_period": "012023",
                "taxable_value": 100,
                "igst": 20,
                "cgst": 20,
                "sgst": 20,
                "cess": 0,
            },
            doc,
        )

    def test_ims_b2ba(self):
        doc = self.get_doc("B2BA", "Invoice")
        print(doc.as_dict())
        self.assertDocumentEqual(
            {
                "bill_date": date(2023, 1, 23),
                "bill_no": "b1a",
                "doc_type": "Invoice",
                "supplier_gstin": "24MAYAS0100J1JD",
                "supply_type": "Regular",
                "classification": "B2BA",
                "place_of_supply": "07-Delhi",
                "original_bill_no": "ab2",
                "original_bill_date": date(2023, 2, 24),
                "is_amended": True,
                "document_value": 1000,
                "is_downloaded_from_ims": 1,
                "ims_action": "Accepted",
                "previous_ims_action": "Accepted",
                "is_pending_action_allowed": 1,
                "is_supplier_return_filed": 0,
                "supplier_return_form": "R1",
                "sup_return_period": "012023",
                "taxable_value": 100,
                "igst": 20,
                "cgst": 20,
                "sgst": 20,
                "cess": 0,
            },
            doc,
        )

    def test_ims_dn(self):
        doc = self.get_doc("CDNR", "Debit Note")
        print(doc.as_dict())
        self.assertDocumentEqual(
            {
                "bill_date": date(2023, 2, 24),
                "bill_no": "dn2",
                "doc_type": "Debit Note",
                "supplier_gstin": "24MAYAS0100J1JD",
                "supply_type": "Regular",
                "classification": "CDNR",
                "place_of_supply": "07-Delhi",
                "document_value": 1000.1,
                "is_downloaded_from_ims": 1,
                "ims_action": "Accepted",
                "previous_ims_action": "Accepted",
                "is_pending_action_allowed": 1,
                "is_supplier_return_filed": 1,
                "supplier_return_form": "R1",
                "sup_return_period": "012023",
                "taxable_value": 1000.1,
                "igst": 20,
                "cgst": 20,
                "sgst": 20,
                "cess": 0,
            },
            doc,
        )

    def test_ims_dna(self):
        doc = self.get_doc("CDNRA", "Debit Note")
        print(doc.as_dict())
        self.assertDocumentEqual(
            {
                "bill_no": "dna2",
                "bill_date": date(2023, 2, 24),
                "original_bill_no": "dn2",
                "original_bill_date": date(2023, 2, 24),
                "doc_type": "Debit Note",
                "supplier_gstin": "24MAYAS0100J1JD",
                "supply_type": "Regular",
                "classification": "CDNRA",
                "place_of_supply": "07-Delhi",
                "is_amended": True,
                "document_value": 1000.1,
                "is_downloaded_from_ims": 1,
                "ims_action": "Accepted",
                "previous_ims_action": "Accepted",
                "is_pending_action_allowed": 1,
                "is_supplier_return_filed": 1,
                "supplier_return_form": "R1",
                "sup_return_period": "012023",
                "taxable_value": 1000.1,
                "igst": 20,
                "cgst": 20,
                "sgst": 20,
                "cess": 0,
            },
            doc,
        )

    def test_ims_cn(self):
        doc = self.get_doc("CDNR", "Credit Note")
        print(doc.as_dict())
        self.assertDocumentEqual(
            {
                "bill_date": date(2023, 2, 24),
                "bill_no": "cn2",
                "doc_type": "Credit Note",
                "supplier_gstin": "24MAYAS0100J1JD",
                "supply_type": "Regular",
                "classification": "CDNR",
                "place_of_supply": "07-Delhi",
                "document_value": 1000.1,
                "is_downloaded_from_ims": 1,
                "ims_action": "Accepted",
                "previous_ims_action": "Accepted",
                "is_pending_action_allowed": 1,
                "is_supplier_return_filed": 0,
                "supplier_return_form": "R1",
                "sup_return_period": "012023",
                "taxable_value": 1000.1,
                "igst": 20,
                "cgst": 20,
                "sgst": 20,
                "cess": 0,
            },
            doc,
        )

    def test_ims_cna(self):
        doc = self.get_doc("CDNRA", "Credit Note")
        print(doc.as_dict())
        self.assertDocumentEqual(
            {
                "bill_no": "cna2",
                "bill_date": date(2023, 2, 24),
                "original_bill_no": "cn2",
                "original_bill_date": date(2023, 2, 24),
                "doc_type": "Credit Note",
                "supplier_gstin": "24MAYAS0100J1JD",
                "supply_type": "Regular",
                "classification": "CDNRA",
                "place_of_supply": "07-Delhi",
                "is_amended": True,
                "document_value": 1000.1,
                "is_downloaded_from_ims": 1,
                "ims_action": "Accepted",
                "previous_ims_action": "Accepted",
                "is_pending_action_allowed": 1,
                "is_supplier_return_filed": 0,
                "supplier_return_form": "R1",
                "sup_return_period": "012023",
                "taxable_value": 1000.1,
                "igst": 20,
                "cgst": 20,
                "sgst": 20,
                "cess": 0,
            },
            doc,
        )
