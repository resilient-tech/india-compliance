# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    toggle_scheduled_jobs,
)

DOWNLOAD_JOB = "india_compliance.gst_india.utils.gstr_utils.download_queued_request"


class TestGSTRImportLog(IntegrationTestCase):
    def test_toggle_scheduled_jobs(self):
        """`stopped` is a Check column, so it has to be written as 0/1 -- postgres rejects a
        bool there, and the callers pass one."""
        job = frappe.db.get_value("Scheduled Job Type", {"method": DOWNLOAD_JOB})
        if not job:
            self.skipTest("download_queued_request scheduled job is not set up on this site")

        toggle_scheduled_jobs(stopped=True)
        self.assertEqual(frappe.db.get_value("Scheduled Job Type", job, "stopped"), 1)

        toggle_scheduled_jobs(stopped=False)
        self.assertEqual(frappe.db.get_value("Scheduled Job Type", job, "stopped"), 0)
