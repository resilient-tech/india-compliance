# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from india_compliance.gst_india.overrides.party import get_pancard_status


class Pan(Document):
    @frappe.whitelist()
    def update_pan_status(self):
        get_pancard_status(self.pan, True)
        frappe.msgprint("PAN Status Updated")
