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
    GSTIN = "24AAQCA8719H1ZC"
    POSTING_DATE = "2099-04-15"

    def setUp(self):
        # the log is created by the test that needs it: test_add_comment asserts there is none
        self.log_name = f"GSTR1-{getdate(self.POSTING_DATE).strftime('%m%Y')}-{self.GSTIN}"

    def test_add_comment_creates_log_when_missing(self):
        self.assertFalse(frappe.db.exists("GST Return Log", self.log_name))

        doc = frappe._dict(
            {
                "posting_date": getdate(self.POSTING_DATE),
                "company_gstin": self.GSTIN,
                "doctype": "Purchase Invoice",
                "name": "PINV-TEST-0001",
            }
        )

        add_comment_to_gst_return_log(doc, "submitted")

        self.assertTrue(frappe.db.exists("GST Return Log", self.log_name))

        comment = frappe.get_value(
            "Comment",
            {
                "reference_doctype": "GST Return Log",
                "reference_name": self.log_name,
            },
            ["name", "content"],
            as_dict=True,
            order_by="creation desc",
        )
        self.assertTrue(comment)
        self.assertIn("has been submitted by", comment.content)

    @patch("india_compliance.gst_india.utils.gstr_1.gstr_1_download.GSTR1API")
    def test_download_gstr1_json_data(self, mock_api):
        """`is_nil` is a Check column, so `isnil` off the downloaded payload has to be stored as
        0/1 -- postgres rejects a bool on a smallint. The API is mocked as the GSTR-2A tests do."""
        log = get_gst_return_log(self.log_name, filing_preference="Monthly")

        for isnil, expected in (("Y", 1), ("N", 0)):
            mock_api.return_value = Mock()
            mock_api.return_value.get_gstr_1_data.return_value = frappe._dict(
                isnil=isnil, error_type=None, token=None
            )

            download_gstr1_json_data(log)

            stored = frappe.db.get_value("GST Return Log", self.log_name, "is_nil")
            self.assertEqual(stored, expected)
            self.assertNotIsInstance(stored, bool, "is_nil must be stored as 0/1, not a bool")
