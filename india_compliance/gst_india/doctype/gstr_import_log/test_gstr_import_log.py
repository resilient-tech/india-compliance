# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.gstr_import_log.gstr_import_log import (
    DOWNLOAD_QUEUED_REQUEST_JOB,
    toggle_scheduled_jobs,
)


class TestGSTRImportLog(IntegrationTestCase):
    def test_toggle_scheduled_jobs(self):
        job = frappe.db.get_value("Scheduled Job Type", {"method": DOWNLOAD_QUEUED_REQUEST_JOB})
        self.assertTrue(job)

        old_value = frappe.db.get_value("Scheduled Job Type", job, "stopped")
        self.addCleanup(frappe.db.set_value, "Scheduled Job Type", job, "stopped", old_value)

        toggle_scheduled_jobs(stopped=True)
        self.assertEqual(frappe.db.get_value("Scheduled Job Type", job, "stopped"), 1)

        toggle_scheduled_jobs(stopped=False)
        self.assertEqual(frappe.db.get_value("Scheduled Job Type", job, "stopped"), 0)
