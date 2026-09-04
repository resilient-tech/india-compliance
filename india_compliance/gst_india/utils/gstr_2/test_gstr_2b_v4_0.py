from datetime import date

import frappe
from frappe import parse_json, read_file
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils import (
    get_data_file_path,
    get_party_for_gstin,
    merge_dicts,
)
from india_compliance.gst_india.utils.gstr_2 import GSTRCategory, save_gstr_2b
from india_compliance.gst_india.utils.gstr_2.gstr import get_unique_key
from india_compliance.gst_india.utils.gstr_2.gstr_2b import GSTR2b
from india_compliance.gst_india.utils.gstr_2.test_gstr_2a import TestGSTRMixin


class TestGSTR2b(TestGSTRMixin, IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.gstin = "01AABCE2207R1Z5"
        cls.return_period = "032020"
        cls.doctype = "GST Inward Supply"
        cls.log_doctype = "GSTR Import Log"
        cls.test_data = parse_json(read_file(get_data_file_path("test_gstr_2b_v4_0.json")))

        save_gstr_2b(
            cls.gstin,
            cls.return_period,
            cls.test_data,
        )

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
                "irn_number": ("897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"),
                "irn_gen_date": date(2019, 12, 24),
                "doc_type": "Invoice",
                "taxable_value": 12200,
                "igst": 183,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
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
                "taxable_value": 12200,
                "igst": 183,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2b_ecom(self):
        doc = self.get_doc(GSTRCategory.ECOM)
        self.assertDocumentEqual(
            {
                "supplier_gstin": "07USERR0205A1ZS",
                "supplier_name": "GSTN",
                "gstr_1_filing_date": date(2023, 8, 26),
                "sup_return_period": "052023",
                "bill_no": "E123",
                "supply_type": "Regular",
                "bill_date": date(2023, 5, 1),
                "document_value": 234324234,
                "place_of_supply": "23-Madhya Pradesh",
                "is_reverse_charge": 0,
                "itc_availability": "Yes",
                "diffprcnt": "1",
                "irn_source": "e-Invoice",
                "irn_number": ("897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"),
                "irn_gen_date": date(2019, 12, 24),
                "doc_type": "Invoice",
                "taxable_value": 12200,
                "igst": 183,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2b_ecoma(self):
        doc = self.get_doc(GSTRCategory.ECOMA)
        self.assertDocumentEqual(
            {
                "supplier_gstin": "07USERR0205A1ZS",
                "supplier_name": "GSTN",
                "gstr_1_filing_date": date(2023, 8, 26),
                "sup_return_period": "052023",
                "bill_no": "E123",
                "supply_type": "Regular",
                "bill_date": date(2023, 5, 1),
                "document_value": 234324234,
                "place_of_supply": "23-Madhya Pradesh",
                "is_reverse_charge": 0,
                "itc_availability": "Yes",
                "diffprcnt": "1",
                "original_bill_no": None,
                "original_bill_date": None,
                "doc_type": "Invoice",
                "taxable_value": 12200,
                "igst": 183,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
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
                "irn_number": ("897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"),
                "irn_gen_date": date(2019, 12, 24),
                "doc_type": "Credit Note",
                "taxable_value": 12200,
                "igst": 183,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
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
                "taxable_value": 12200,
                "igst": 183,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2b_isd(self):
        doc = self.get_doc(GSTRCategory.ISD, supplier_gstin="16DEFPS8555D1Z7")
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
                "igst": 0,
                "cgst": 200,
                "sgst": 200,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_rejecting_one_isd_document_leaves_the_other(self):
        """A rejected document is deleted by bill no, date, classification and supplier -- which one
        ISD numbering series can carry twice, once as an invoice and once as a credit note. Without
        the document type the wrong one goes."""
        filters = {"supplier_gstin": "27AABCE2207R1Z5", "bill_no": "S9001"}
        invoice = self.get_doc(GSTRCategory.ISD, **filters, doc_type="ISD Invoice")
        credit_note = self.get_doc(GSTRCategory.ISD, **filters, doc_type="ISD Credit Note")

        rejected = frappe._dict(
            data=frappe._dict(
                gstin=self.gstin,
                gendt=self.test_data["data"]["gendt"],
                docdata={},
                docRejdata={
                    "isd": [
                        {
                            "ctin": "27AABCE2207R1Z5",
                            "trdnm": "GSTN Mixed Eligibility",
                            "supprd": "022020",
                            "supfildt": "02-03-2020",
                            "doclist": [
                                {
                                    "doctyp": "ISDC",
                                    "docnum": "S9001",
                                    "docdt": "03-03-2016",
                                    "igst": 0,
                                    "cgst": 50,
                                    "sgst": 50,
                                    "cess": 0,
                                    "itcelg": "Y",
                                }
                            ],
                        }
                    ]
                },
            )
        )
        save_gstr_2b(self.gstin, self.return_period, rejected, store_raw=False)

        self.assertFalse(frappe.db.exists(self.doctype, credit_note.name))
        self.assertTrue(frappe.db.exists(self.doctype, invoice.name))

    def test_gstr2b_isda(self):
        doc = self.get_doc(GSTRCategory.ISDA, supplier_gstin="16DEFPS8555D1Z7")
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
                "igst": 0,
                "cgst": 200,
                "sgst": 200,
                "cess": 0,
                "is_downloaded_from_2b": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2b_isd_groups_by_document_not_by_number(self):
        """Supplier 27AABCE2207R1Z5 reports three rows, all numbered S9001: an invoice split into
        its eligible and ineligible halves per Rule 39(1)(b), and a credit note from the same
        series. The halves belong to one invoice and have to fold together; the credit note is a
        different document and has to stay apart."""
        stored = {
            doc.doc_type: doc
            for doc in frappe.get_all(
                self.doctype,
                filters={
                    "company_gstin": self.gstin,
                    "classification": GSTRCategory.ISD.value,
                    "supplier_gstin": "27AABCE2207R1Z5",
                },
                fields=["name", "doc_type", "bill_no", "cgst", "sgst", "itc_availability"],
            )
        }

        self.assertEqual(set(stored), {"ISD Invoice", "ISD Credit Note"})

        invoice = frappe.get_doc(self.doctype, stored["ISD Invoice"].name)
        self.assertEqual(invoice.bill_no, "S9001")
        # both halves survive as rows, and the totals are their sum
        self.assertEqual(len(invoice.items), 2)
        self.assertEqual({item.itcelg for item in invoice.items}, {"Y", "N"})
        self.assertEqual(invoice.cgst, 300)
        self.assertEqual(invoice.sgst, 300)
        self.assertEqual(invoice.document_value, 600)
        # the rows carry the eligibility; the document keeps what the portal reported for the part
        # it arrived under
        self.assertEqual(invoice.itc_availability, "Yes")

        credit_note = stored["ISD Credit Note"]
        self.assertEqual(credit_note.bill_no, "S9001")
        self.assertEqual(credit_note.cgst, 50)
        self.assertEqual(credit_note.sgst, 50)

    def test_gstr2b_isd_keeps_two_distributors_apart(self):
        """Two ISDs number their documents from their own series, so the same number, type and date
        can arrive from both in one 2B. Folding the parts of one document together must not fold two
        suppliers' documents into one, or one distributor is credited with the other's ITC."""
        credit = {"29AABCE2207R1Z5": 100, "24AABCE2207R1Z5": 250}
        suppliers = [
            {
                "ctin": supplier_gstin,
                "trdnm": f"Distributor {supplier_gstin}",
                "supprd": "022020",
                "supfildt": "02-03-2020",
                "doclist": [
                    {
                        "doctyp": "ISDI",
                        "docnum": "ISD-77",
                        "docdt": "03-03-2016",
                        "igst": 0,
                        "cgst": cgst,
                        "sgst": cgst,
                        "cess": 0,
                        "itcelg": "Y",
                    }
                ],
            }
            for supplier_gstin, cgst in credit.items()
        ]

        gstr = GSTR2b(
            get_party_for_gstin(self.gstin, "Company"),
            self.gstin,
            self.return_period,
            GSTRCategory.ISD.value,
        )
        transactions = {t.supplier_gstin: t for t in gstr.get_all_transactions(suppliers)}

        self.assertEqual(set(transactions), set(credit))

        for supplier_gstin, cgst in credit.items():
            transaction = transactions[supplier_gstin]
            self.assertEqual(transaction.bill_no, "ISD-77")
            self.assertEqual(transaction.cgst, cgst)
            self.assertEqual(transaction.sgst, cgst)
            self.assertEqual(transaction.document_value, cgst * 2)

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
                "taxable_value": 123.02,
                "igst": 123.02,
                "cess": 0.5,
                "is_downloaded_from_2b": 1,
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
                "taxable_value": 123.02,
                "igst": 123.02,
                "cess": 0.5,
                "is_downloaded_from_2b": 1,
            },
            doc,
        )

    def test_impg_return_period_persists_on_redownload(self):
        """
        A 2B re-download must not clear return_period_2b for IMPG rows.
        """
        doc = self.get_doc(GSTRCategory.IMPG)
        self.assertEqual(doc.return_period_2b, self.return_period)
        self.assertEqual(doc.is_downloaded_from_2b, 1)

        save_gstr_2b(self.gstin, self.return_period, self.test_data)

        doc.reload()
        self.assertEqual(doc.return_period_2b, self.return_period)
        self.assertEqual(doc.is_downloaded_from_2b, 1)


class TestGetUniqueKey(IntegrationTestCase):
    def test_null_gstin_matches_empty_gstin(self):
        # DB row with NULL supplier_gstin -> None, vs incoming with field absent
        existing = frappe._dict(supplier_gstin=None, bill_no="2566282")
        incoming = frappe._dict(bill_no="2566282")
        self.assertEqual(get_unique_key(existing), get_unique_key(incoming))
        self.assertEqual(get_unique_key(existing), "-2566282-")

    def test_normal_gstin(self):
        t = frappe._dict(supplier_gstin="01AABCE2207R1Z5", bill_no="INV-1")
        self.assertEqual(get_unique_key(t), "01AABCE2207R1Z5-INV-1-")

    def test_doc_type_separates_an_isd_invoice_from_its_credit_note(self):
        """create_inward_supply keys on doc_type, so the existing-transaction map has to as well:
        an ISD numbers both from one series, and a collision leaves the stale row behind."""
        gstin, bill_no = "01AABCE2207R1Z5", "ISD-1"
        invoice = frappe._dict(supplier_gstin=gstin, bill_no=bill_no, doc_type="ISD Invoice")
        credit_note = frappe._dict(supplier_gstin=gstin, bill_no=bill_no, doc_type="ISD Credit Note")

        self.assertNotEqual(get_unique_key(invoice), get_unique_key(credit_note))


class TestMultiFileRawMerge(IntegrationTestCase):
    def test_docs_concat_summary_not_doubled(self):
        combined = {}
        file1 = {"itcsumm": {"itcavl": 100}, "docdata": {"b2b": [{"inum": "1"}]}}
        file2 = {"itcsumm": {"itcavl": 150}, "docdata": {"b2b": [{"inum": "2"}], "cdnr": [{"nt": "9"}]}}
        merge_dicts(combined, file1)
        merge_dicts(combined, file2)

        self.assertEqual(combined["docdata"]["b2b"], [{"inum": "1"}, {"inum": "2"}])
        self.assertEqual(combined["docdata"]["cdnr"], [{"nt": "9"}])
        self.assertEqual(combined["itcsumm"]["itcavl"], 150)
