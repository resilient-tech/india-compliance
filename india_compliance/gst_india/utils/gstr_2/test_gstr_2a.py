from datetime import date, timedelta
from unittest.mock import Mock, patch

import frappe
from frappe import parse_json, read_file
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr_2 import (
    GSTRCategory,
    ReturnType,
    download_gstr_2a,
    save_gstr_2a,
)


class TestGSTRMixin:
    def get_doc(self, category):
        docname = frappe.get_value(
            self.doctype,
            {"company_gstin": self.gstin, "classification": category.value},
        )
        self.assertIsNotNone(docname)
        return frappe.get_doc(self.doctype, docname)

    def assertImportLog(self, category=None):
        if category:
            return_type = ReturnType.GSTR2A
        else:
            return_type = ReturnType.GSTR2B

        filters = {"gstin": self.gstin, "return_type": return_type}
        if category:
            filters["classification"] = category.value

        docname, last_updated_on = frappe.get_value(self.log_doctype, filters, ["name", "last_updated_on"])
        self.assertIsNotNone(docname)
        self.assertAlmostEqual(last_updated_on, get_datetime(), delta=timedelta(minutes=2))


class TestGSTR2a(TestGSTRMixin, FrappeTestCase):
    # Tests as per version 2.1 of GSTR2A Dt: 14-10-2020
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.gstin = "01AABCE2207R1Z5"
        cls.return_period = "032020"
        cls.doctype = "GST Inward Supply"
        cls.log_doctype = "GSTR Import Log"
        cls.test_data = parse_json(read_file(get_data_file_path("test_gstr_2a.json")))

        save_gstr_2a(
            cls.gstin,
            cls.return_period,
            cls.test_data.copy(),
        )

    @patch("india_compliance.gst_india.utils.gstr_2.save_gstr")
    @patch("india_compliance.gst_india.utils.gstr_2.GSTR2aAPI")
    def test_download_gstr_2a(self, mock_gstr_2a_api, mock_save_gstr):

        def mock_get_data(action, return_period):
            if action in ["B2B", "B2BA", "CDN", "CDNA", "ECOM", "ECOMA", "TDS", "TCS"]:
                return frappe._dict({action.lower(): self.test_data[action.lower()]})
            else:
                return frappe._dict(error_type="no_docs_found")

        def mock_save_gstr_func(gstin, return_type, return_period, json_data):
            self.assertEqual(gstin, self.gstin)
            self.assertEqual(return_period, self.return_period)
            self.assertTrue("cdnr" in json_data)
            self.assertTrue("cdnra" in json_data)
            self.assertTrue("isd" not in json_data)
            self.assertListEqual(json_data.cdnr, self.test_data.cdn)
            for category in ("ecom", "ecoma", "tds", "tcs"):
                self.assertTrue(category in json_data)
                self.assertListEqual(json_data[category], self.test_data[category])

        mock_gstr_2a_api.return_value = Mock()
        mock_gstr_2a_api.return_value.get_data.side_effect = mock_get_data
        mock_save_gstr.side_effect = mock_save_gstr_func
        download_gstr_2a(self.gstin, (self.return_period,))

    def test_gstr2a_b2b(self):
        doc = self.get_doc(GSTRCategory.B2B)
        self.assertImportLog(GSTRCategory.B2B)
        self.assertDocumentEqual(
            {
                "bill_date": date(2016, 11, 24),
                "bill_no": "S008400",
                "doc_type": "Invoice",
                "supplier_gstin": "01AABCE2207R1Z5",
                "supply_type": "Regular",
                "place_of_supply": "06-Haryana",
                "items": [
                    {
                        "item_number": 1,
                        "taxable_value": 400,
                        "rate": 5.00,
                        "igst": 0,
                        "cgst": 200,
                        "sgst": 200,
                        "cess": 0,
                    },
                ],
                "document_value": 729248.16,
                "diffprcnt": "1",
                "other_return_period": "122018",
                "amendment_type": "Receiver GSTIN Amended",
                "sup_return_period": "112019",
                "gstr_1_filled": 1,
                "gstr_3b_filled": 1,
                "gstr_1_filing_date": date(2019, 11, 18),
                "registration_cancel_date": date(2019, 8, 27),
                "is_downloaded_from_2a": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2a_b2ba(self):
        doc = self.get_doc(GSTRCategory.B2BA)
        self.assertImportLog(GSTRCategory.B2BA)
        self.assertDocumentEqual(
            {
                "bill_date": date(2016, 11, 24),
                "bill_no": "S008400",
                "doc_type": "Invoice",
                "supplier_gstin": "01AABCE2207R1Z5",
                "supply_type": "Regular",
                "place_of_supply": "06-Haryana",
                "items": [
                    {
                        "item_number": 1,
                        "taxable_value": 6210.99,
                        "rate": 1.00,
                        "igst": 0,
                        "cgst": 614.44,
                        "sgst": 5.68,
                        "cess": 621.09,
                    },
                    {
                        "item_number": 2,
                        "taxable_value": 1000.05,
                        "rate": 2.00,
                        "igst": 0,
                        "cgst": 887.44,
                        "sgst": 5.68,
                        "cess": 50.12,
                    },
                ],
                "document_value": 729248.16,
                "diffprcnt": "0.65",
                "other_return_period": "122018",
                "amendment_type": "Receiver GSTIN Amended",
                "original_bill_no": "S008400",
                "original_bill_date": date(2016, 11, 24),
                "is_amended": 1,
                "sup_return_period": "042018",
                "gstr_1_filled": 1,
                "gstr_3b_filled": 1,
                "gstr_1_filing_date": date(2020, 5, 12),
                "registration_cancel_date": date(2019, 8, 27),
                "is_downloaded_from_2a": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2a_cdn(self):
        doc = self.get_doc(GSTRCategory.CDNR)
        self.assertImportLog(GSTRCategory.CDNR)
        self.assertDocumentEqual(
            {
                "bill_date": date(2018, 9, 23),
                "bill_no": "533515",
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
                "gstr_1_filing_date": date(2020, 5, 12),
                "registration_cancel_date": date(2019, 8, 27),
                "irn_source": "e-Invoice",
                "irn_number": ("897ADG56RTY78956HYUG90BNHHIJK453GFTD99845672FDHHHSHGFH4567FG56TR"),
                "irn_gen_date": date(2019, 12, 24),
                "is_downloaded_from_2a": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2a_cdna(self):
        doc = self.get_doc(GSTRCategory.CDNRA)
        self.assertImportLog(GSTRCategory.CDNRA)
        self.assertDocumentEqual(
            {
                "bill_date": date(2018, 9, 23),
                "bill_no": "533515",
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
                "original_bill_no": "533515",
                "original_bill_date": date(2016, 9, 23),
                "original_doc_type": "Credit Note",
                "sup_return_period": "112019",
                "gstr_1_filled": 1,
                "gstr_3b_filled": 1,
                "gstr_1_filing_date": date(2019, 11, 18),
                "registration_cancel_date": date(2019, 8, 27),
                "is_downloaded_from_2a": 1,
                "is_supplier_return_filed": 1,
            },
            doc,
        )

    def test_gstr2a_isd(self):
        doc = self.get_doc(GSTRCategory.ISD)
        self.assertImportLog(GSTRCategory.ISD)
        self.assertDocumentEqual(
            {
                "bill_date": date(2016, 3, 3),
                "bill_no": "S0080",
                "doc_type": "ISD Invoice",
                "supplier_gstin": "16DEFPS8555D1Z7",
                "itc_availability": "Yes",
                "other_return_period": "122018",
                "amendment_type": "Receiver GSTIN Amended",
                "is_amended": 1,
                "document_value": 80,
                "igst": 20,
                "cgst": 20,
                "sgst": 20,
                "cess": 20,
                "is_downloaded_from_2a": 1,
            },
            doc,
        )

    def test_gstr2a_isda(self):
        # No such API exists. Its merged with ISD.
        pass

    def test_gstr2a_impg(self):
        doc = self.get_doc(GSTRCategory.IMPG)
        self.assertImportLog(GSTRCategory.IMPG)
        self.assertDocumentEqual(
            {
                "bill_date": date(2019, 11, 18),
                "port_code": "18272A",
                "bill_no": "2566282",
                "doc_type": "Bill of Entry",
                "is_amended": 0,
                "document_value": 246.54,
                "taxable_value": 123.02,
                "igst": 123.02,
                "cess": 0.5,
                "is_downloaded_from_2a": 1,
            },
            doc,
        )

    def test_gstr2a_impgsez(self):
        doc = self.get_doc(GSTRCategory.IMPGSEZ)
        self.assertImportLog(GSTRCategory.IMPGSEZ)
        self.assertDocumentEqual(
            {
                "bill_date": date(2019, 11, 18),
                "port_code": "18272A",
                "bill_no": "2566282",
                "doc_type": "Bill of Entry",
                "supplier_gstin": self.gstin,
                "supplier_name": "GSTN",
                "is_amended": 0,
                "document_value": 246.54,
                "taxable_value": 123.02,
                "igst": 123.02,
                "cgst": 0,
                "sgst": 0,
                "cess": 0.5,
                "is_downloaded_from_2a": 1,
            },
            doc,
        )

    def test_gstr2a_ecom(self):
        doc = self.get_doc(GSTRCategory.ECOM)
        self.assertImportLog(GSTRCategory.ECOM)
        self.assertDocumentEqual(
            {
                "bill_no": "ECO-001",
                "bill_date": date(2019, 11, 24),
                "doc_type": "Invoice",
                "supplier_gstin": self.gstin,
                "supply_type": "Regular",
                "place_of_supply": "06-Haryana",
                "document_value": 1180,
                "taxable_value": 1000,
                "igst": 0,
                "cgst": 90,
                "sgst": 90,
                "cess": 0,
                "is_downloaded_from_2a": 1,
                "items": [
                    {
                        "item_number": 1,
                        "rate": 18,
                        "taxable_value": 1000,
                        "igst": 0,
                        "cgst": 90,
                        "sgst": 90,
                        "cess": 0,
                    }
                ],
            },
            doc,
        )

    def test_gstr2a_ecoma(self):
        doc = self.get_doc(GSTRCategory.ECOMA)
        self.assertImportLog(GSTRCategory.ECOMA)
        self.assertDocumentEqual(
            {
                "bill_no": "ECO-001-A",
                "bill_date": date(2019, 11, 25),
                "original_bill_no": "ECO-001",
                "original_bill_date": date(2019, 11, 24),
                "doc_type": "Invoice",
                "supplier_gstin": self.gstin,
                "amendment_type": "Receiver GSTIN Amended",
                "document_value": 1180,
                "taxable_value": 1000,
                "cgst": 90,
                "sgst": 90,
                "is_downloaded_from_2a": 1,
            },
            doc,
        )

    def test_gstr2a_tds(self):
        doc = self.get_doc(GSTRCategory.TDS)
        self.assertImportLog(GSTRCategory.TDS)
        self.assertDocumentEqual(
            {
                "supplier_gstin": "24AANFA2543R1ZG",
                "supplier_name": "Test Deductor",
                "sup_return_period": "022020",
                "taxable_value": 10000,
                "igst": 0,
                "cgst": 100,
                "sgst": 100,
                "document_value": 10000,
                "is_downloaded_from_2a": 1,
            },
            doc,
        )

    def test_gstr2a_tcs(self):
        doc = self.get_doc(GSTRCategory.TCS)
        self.assertImportLog(GSTRCategory.TCS)
        self.assertDocumentEqual(
            {
                "supplier_gstin": self.gstin,
                "sup_return_period": self.return_period,
                "taxable_value": 48000,
                "igst": 0,
                "cgst": 240,
                "sgst": 240,
                "cess": 0,
                "document_value": 50000,
                "is_downloaded_from_2a": 1,
            },
            doc,
        )

    def test_gstr2a_tds_tcs_across_periods(self):
        # TDS/TCS records have no bill number/date. Downloading the same deductor
        # (TDS) / collector (TCS) across multiple periods must yield one distinct
        # record per period, not a single record overwritten by the latest period.
        deductor = "27AAPFU0939F1ZV"
        periods = ("052020", "062020")
        section_data = {
            "tds": {"gstin_deductor": deductor, "amt_ded": 10000, "iamt": 0, "camt": 100, "samt": 100},
            "tcs": {
                "etin": deductor,
                "sup_val": 50000,
                "tx_val": 48000,
                "iamt": 0,
                "camt": 240,
                "samt": 240,
                "csamt": 0,
            },
        }

        for section, record in section_data.items():
            for period in periods:
                if section == "tds":
                    record["month"] = period

                save_gstr_2a(
                    self.gstin,
                    period,
                    frappe._dict({"gstin": self.gstin, "fp": period, section: [record]}),
                )

            classification = section.upper()
            stored_periods = frappe.get_all(
                "GST Inward Supply",
                filters={
                    "company_gstin": self.gstin,
                    "classification": classification,
                    "supplier_gstin": deductor,
                },
                pluck="sup_return_period",
            )
            self.assertCountEqual(
                stored_periods,
                periods,
                msg=f"{classification}: expected one record per period, got {stored_periods}",
            )

    def test_gstr2a_ecom_runs_amendment_linking(self):
        # ECOM docs now run the amendment machinery: an ECOM invoice carrying an
        # amendment period (aspd) is stamped match_status="Amended" in before_save.
        save_gstr_2a(
            self.gstin,
            "072020",
            frappe._dict(
                {
                    "gstin": self.gstin,
                    "fp": "072020",
                    "ecom": [
                        {
                            "ctin": self.gstin,
                            "inv": [
                                {
                                    "inum": "ECO-AMD-001",
                                    "idt": "24-07-2020",
                                    "val": 1180,
                                    "pos": "06",
                                    "rchrg": "N",
                                    "inv_typ": "R",
                                    "aspd": "May-20",
                                    "itms": [
                                        {
                                            "num": 1,
                                            "itm_det": {"rt": 18, "txval": 1000, "camt": 90, "samt": 90},
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ),
        )

        doc = frappe.get_doc(
            "GST Inward Supply",
            {"company_gstin": self.gstin, "classification": "ECOM", "bill_no": "ECO-AMD-001"},
        )
        self.assertEqual(doc.other_return_period, "052020")
        self.assertEqual(doc.match_status, "Amended")
