import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.gstr_1.gstr_1_download import (
    get_sections_to_download,
    save_gstr_1,
)


class TestGSTR1Download(IntegrationTestCase):
    def test_get_sections_to_download_nil(self):
        summary = frappe._dict(isnil="Y")
        result = get_sections_to_download(summary)
        self.assertEqual(result, [])

    def test_get_sections_to_download_nil_empty_str(self):
        summary = frappe._dict(isnil="")
        summary["sec_sum"] = []
        result = get_sections_to_download(summary)
        self.assertEqual(result, [])

    def test_get_sections_to_download_maps_b2b(self):
        summary = frappe._dict(isnil="N")
        summary["sec_sum"] = [
            {"sec_nm": "B2B", "ttl_rec": 5},
        ]
        result = get_sections_to_download(summary)
        self.assertIn("B2B", result)

    def test_get_sections_to_download_maps_multiple(self):
        summary = frappe._dict(isnil="N")
        summary["sec_sum"] = [
            {"sec_nm": "B2B", "ttl_rec": 5},
            {"sec_nm": "B2CL", "ttl_rec": 3},
            {"sec_nm": "EXP", "ttl_rec": 1},
        ]
        result = get_sections_to_download(summary)
        self.assertIn("B2B", result)
        self.assertIn("B2CL", result)
        self.assertIn("EXP", result)

    def test_get_sections_to_download_maps_txpd(self):
        summary = frappe._dict(isnil="N")
        summary["sec_sum"] = [
            {"sec_nm": "TXPD", "ttl_rec": 2},
        ]
        result = get_sections_to_download(summary)
        self.assertIn("TXP", result)

    def test_get_sections_to_download_maps_hsn(self):
        summary = frappe._dict(isnil="N")
        summary["sec_sum"] = [
            {"sec_nm": "HSN", "ttl_rec": 4},
        ]
        result = get_sections_to_download(summary)
        self.assertIn("HSNSUM", result)

    def test_get_sections_to_download_maps_doc_issue(self):
        summary = frappe._dict(isnil="N")
        summary["sec_sum"] = [
            {"sec_nm": "DOC_ISSUE", "ttl_rec": 2},
        ]
        result = get_sections_to_download(summary)
        self.assertIn("DOCISS", result)

    def test_get_sections_to_download_skips_zero_records(self):
        summary = frappe._dict(isnil="N")
        summary["sec_sum"] = [
            {"sec_nm": "B2B", "ttl_rec": 5},
            {"sec_nm": "B2CL", "ttl_rec": 0},
            {"sec_nm": "EXP", "ttl_rec": 0},
        ]
        result = get_sections_to_download(summary)
        self.assertIn("B2B", result)
        self.assertNotIn("B2CL", result)
        self.assertNotIn("EXP", result)

    def test_get_sections_to_download_skips_unknown_sections(self):
        summary = frappe._dict(isnil="N")
        summary["sec_sum"] = [
            {"sec_nm": "UNKNOWN_SECTION", "ttl_rec": 5},
        ]
        result = get_sections_to_download(summary)
        self.assertEqual(result, [])

    def test_save_gstr_1_empty_json_data_throws(self):
        with self.assertRaises(frappe.ValidationError):
            save_gstr_1("24AAQCA8719H1ZC", "012025", {}, "GSTR1")
