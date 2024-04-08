# Copyright (c) 2023, Resilient Tech and Contributors
# See license.txt
import re

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import now

from india_compliance.gst_india.utils.tests import create_transaction


class TestGSTIN(FrappeTestCase):
    @change_settings("GST Settings", {"validate_gstin_status": 1, "sandbox_mode": 0})
    def test_validate_gst_transporter_id_info(self):
        # customer gstin
        frappe.get_doc(
            {
                "doctype": "GSTIN",
                "gstin": "24AANFA2641L1ZF",
                "registration_date": "2021-01-01",
                "status": "Active",
                "last_updated_on": now(),
            }
        ).insert(ignore_if_duplicate=True)

        # gst transporter id
        frappe.get_doc(
            {
                "doctype": "GSTIN",
                "gstin": "88AABCM9407D1ZS",
                "status": "Invalid",
                "last_updated_on": now(),
            }
        ).insert(ignore_if_duplicate=True)

        si = create_transaction(
            doctype="Sales Invoice",
            gst_transporter_id="88AABCM9407D1ZS",
            do_not_save=True,
        )

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(
                r"^(.*is not Active. Please make sure that transporter ID is valid.*)$"
            ),
            si.save,
        )
