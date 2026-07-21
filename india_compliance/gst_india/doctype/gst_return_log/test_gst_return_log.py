# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    add_comment_to_gst_return_log,
    get_gst_return_log,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_download import download_gstr1_json_data


class TestGSTReturnLog(IntegrationTestCase):
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


class TestGSTReturnLogIsNil(IntegrationTestCase):
    """`is_nil` is a Check column, so every path that sets it has to store 0/1. Each one derives
    the value from an API response as a bool, which postgres rejects on a smallint. The taxpayer
    API is mocked the same way the GSTR-2A tests do it."""

    GSTIN = "24AAQCA8719H1ZC"
    PERIOD = "042099"

    def setUp(self):
        frappe.set_user("Administrator")
        self.log_name = f"GSTR1-{self.PERIOD}-{self.GSTIN}"
        frappe.db.delete("GST Return Log", {"name": self.log_name})

        self.log = get_gst_return_log(self.log_name, filing_preference="Monthly")

    def assertStoredIsNil(self, expected):
        stored = frappe.db.get_value("GST Return Log", self.log_name, "is_nil")
        self.assertEqual(stored, expected)
        self.assertNotIsInstance(stored, bool, "is_nil must be stored as 0/1, not a bool")

    def test_fetch_and_compare_summary(self):
        """Reads `isnil` off the filed summary."""
        for isnil, expected in (("Y", 1), ("N", 0)):
            api = Mock()
            api.get_gstr_1_data.return_value = frappe._dict(isnil=isnil, error="stop after is_nil")

            self.log.fetch_and_compare_summary(api)
            self.assertStoredIsNil(expected)

    @patch("india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1.GSTR1API")
    def test_reset_gstr1(self, mock_api):
        """Takes the flag from the caller, as a string over the wire."""
        mock_api.return_value = Mock()
        # logged against the GSTR Action row, so it has to be a real value
        mock_api.return_value.request_id = "test-request-id"
        mock_api.return_value.reset_gstr_1_data.return_value = {"reference_id": "test"}

        for is_nil_return, expected in (("1", 1), ("0", 0)):
            self.log.reset_gstr1(is_nil_return, force=True)
            self.assertStoredIsNil(expected)

    @patch("india_compliance.gst_india.utils.gstr_1.gstr_1_download.GSTR1API")
    def test_download_gstr1_json_data(self, mock_api):
        """Reads `isnil` off the downloaded payload."""
        for isnil, expected in (("Y", 1), ("N", 0)):
            mock_api.return_value = Mock()
            mock_api.return_value.get_gstr_1_data.return_value = frappe._dict(
                isnil=isnil, error_type=None, token=None
            )

            download_gstr1_json_data(self.log)
            self.assertStoredIsNil(expected)
