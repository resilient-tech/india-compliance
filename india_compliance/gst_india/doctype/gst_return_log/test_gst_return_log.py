# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import copy
import io
from unittest.mock import Mock, patch

import frappe
import openpyxl
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    ReconcileGSTR1,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    add_comment_to_gst_return_log,
    get_gst_return_log,
    get_raw_return_data,
    store_raw_return_data,
)
from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_export import ReconcileExcel
from india_compliance.gst_india.utils.gstr_1 import (
    DocField,
    JsonKey,
    RawField,
    SheetName,
    SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    download_gstr1_json_data,
    save_gstr_1,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_internal_data_format,
)


class TestGSTReturnLog(FrappeTestCase):
    def test_add_comment_creates_log_when_missing(self):
        gstin = "24AAQCA8719H1ZC"
        posting_date = getdate("2099-04-15")
        period = posting_date.strftime("%m%Y")
        log_name = f"GSTR1-{period}-{gstin}"

        self.assertFalse(frappe.db.exists("GST Return Log", log_name))

        doc = frappe._dict(
            {
                "posting_date": posting_date,
                "company_gstin": gstin,
                "doctype": "Purchase Invoice",
                "name": "PINV-TEST-0001",
            }
        )

        add_comment_to_gst_return_log(doc, "submitted")

        self.assertTrue(frappe.db.exists("GST Return Log", log_name))

        comment = frappe.get_value(
            "Comment",
            {
                "reference_doctype": "GST Return Log",
                "reference_name": log_name,
            },
            ["name", "content"],
            as_dict=True,
            order_by="creation desc",
        )
        self.assertTrue(comment)
        self.assertIn("has been submitted by", comment.content)

    def test_portal_data_roundtrip(self):
        gstin = "24AAQCA8719H1ZC"
        payload = {
            "gstin": gstin,
            "b2b": [{"ctin": "24AABCR6898M1ZN", "txval": 100.0, "iamt": 0}],
            "itcsumm": {"itcavl": []},
        }
        original = copy.deepcopy(payload)

        self.assertIsNone(get_raw_return_data(gstin, "GSTR2b", "052099"))

        store_raw_return_data(gstin, "GSTR2b", "052099", payload)
        got = get_raw_return_data(gstin, "GSTR2b", "052099")

        self.assertEqual(got, original)

    @patch("india_compliance.gst_india.utils.gstr_1.gstr_1_download.GSTR1API")
    def test_filed_gstr1_stores_raw(self, mock_api):
        """Filed GSTR-1 keeps the portal payload as received. Unfiled does not."""
        gstin = "24AAQCA8719H1ZC"
        period = "052099"
        log_name = f"GSTR1-{period}-{gstin}"
        raw = frappe._dict(isnil="N", error_type=None, token=None, chksum="abc123")

        mock_api.return_value = Mock()
        mock_api.return_value.get_gstr_1_data.return_value = raw

        log = get_gst_return_log(log_name, filing_preference="Monthly")
        download_gstr1_json_data(log)
        self.assertIsNone(get_raw_return_data(gstin, "GSTR1", period))

        log.db_set("filing_status", "Filed")
        download_gstr1_json_data(frappe.get_doc("GST Return Log", log_name))

        stored = get_raw_return_data(gstin, "GSTR1", period)
        self.assertEqual(stored["chksum"], "abc123")
        self.assertNotIn("creation", stored)

        save_gstr_1(
            gstin,
            period,
            {"b2b": [{"ctin": "24AABCR6898M1ZN", "inv": []}]},
            "GSTR1",
        )
        stored = get_raw_return_data(gstin, "GSTR1", period)
        self.assertEqual(stored["chksum"], "abc123")
        self.assertIn("b2b", stored)

        download_gstr1_json_data(frappe.get_doc("GST Return Log", log_name))
        stored = get_raw_return_data(gstin, "GSTR1", period)
        self.assertEqual(stored["chksum"], "abc123")
        self.assertNotIn("b2b", stored)

    def test_reconcile_compares_amounts_the_portal_sent_as_null(self):
        """An amount can be None or missing. Books value must still show as a mismatch."""
        books_row = {
            "document_number": "S1",
            "total_taxable_value": 100,
            "total_igst_amount": 18,
            "total_cess_amount": 5,
        }
        gov_row = {
            "document_number": "S1",
            "total_taxable_value": 100,
            "total_igst_amount": None,
        }

        reconciled = ReconcileGSTR1.get_reconciled_row(books_row, gov_row)

        self.assertEqual(reconciled["match_status"], "Mismatch")
        self.assertEqual(reconciled["total_igst_amount"], 18)
        self.assertEqual(reconciled["total_cess_amount"], 5)
        self.assertIn("Total Igst Amount", reconciled["differences"])
        self.assertIn("Total Cess Amount", reconciled["differences"])

    def test_a_document_range_holding_a_draft_reconciles(self):
        """We file a draft as cancelled, so both sides agree and the range matches."""
        books_row = {
            "document_type": "Invoices for outward supply",
            "total_count": 5,
            "cancelled_count": 1,
            "draft_count": 1,
            "net_issue": 3,
        }
        gov_row = {
            "document_type": "Invoices for outward supply",
            "total_count": 5,
            "cancelled_count": 2,  # our cancelled one plus our draft
            "net_issue": 3,
        }

        self.assertIsNone(ReconcileGSTR1.get_reconciled_row(books_row, gov_row))

    def test_a_genuinely_extra_cancellation_is_still_reported(self):
        """One more cancelled than the portal knows about must still show."""
        books_row = {
            "document_type": "Invoices for outward supply",
            "total_count": 5,
            "cancelled_count": 2,
            "draft_count": 1,
            "net_issue": 2,
        }
        gov_row = {
            "document_type": "Invoices for outward supply",
            "total_count": 5,
            "cancelled_count": 2,
            "net_issue": 3,
        }

        reconciled = ReconcileGSTR1.get_reconciled_row(books_row, gov_row)

        self.assertEqual(reconciled["match_status"], "Mismatch")
        self.assertIn("Cancelled Count", reconciled["differences"])
        self.assertIn("Net Issue", reconciled["differences"])
        self.assertNotIn("Draft Count", reconciled["differences"])

    def test_a_blank_portal_amount_reconciles_and_exports(self):
        """The portal can send IGST as null: it stays blank, yet reconcile, aggregation and the Excel treat it as 0."""
        gstin = "24AAQCA8719H1ZC"
        log = get_gst_return_log(f"GSTR1-062099-{gstin}", filing_preference="Monthly")
        row = {
            RawField.SUPPLY_TYPE: "INTER",
            RawField.POS: "27",
            RawField.TYPE: "OE",
            RawField.TAX_RATE: 18,
            RawField.TAXABLE_VALUE: 100,
            RawField.IGST: 18,
            RawField.CESS: 0,
        }
        books = convert_to_internal_data_format({JsonKey.B2CS.value: [row]})
        gov = convert_to_internal_data_format(
            {
                JsonKey.B2CS.value: [
                    {**row, RawField.TAXABLE_VALUE: 102, RawField.IGST: None},
                    {**row, RawField.POS: "33", RawField.IGST: None},
                ]
            }
        )

        gov_rows = gov[SubCategory.B2CS.value].values()
        self.assertEqual([r[0][DocField.IGST] for r in gov_rows], [None, None])

        reconcile = log.normalize_data(log.get_reconcile_gstr1_data(gov, books))
        aggregated = log.get_aggregate_data(books)[SubCategory.B2CS.value]
        self.assertEqual(sorted(r[0][DocField.IGST] for r in aggregated.values()), [0, 18])

        log.summarize_data({"reconcile": reconcile}, frappe._dict(month_or_quarter="June", year="2099"))
        ReconcileExcel(gstin, "June", "2099").export_data()

        sheet = openpyxl.load_workbook(io.BytesIO(frappe.local.response.filecontent))[SheetName.B2CS.value]
        rows = [[cell.value for cell in row] for row in sheet.iter_rows()]
        column = rows[1].index("Tax Difference")
        self.assertEqual(sorted(row[column] for row in rows[2:]), [0, 18])
