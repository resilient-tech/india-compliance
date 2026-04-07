# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import add_comment_to_gst_return_log


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
