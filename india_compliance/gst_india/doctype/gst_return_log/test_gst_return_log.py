# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import copy

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    add_comment_to_gst_return_log,
    get_raw_return_data,
    store_raw_return_data,
)


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

        got.pop("creation", None)
        self.assertEqual(got, original)
