# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe

from india_compliance.income_tax_india.utils.msme import get_msme_classification

# class extensions for virtual fields


class MSMEDetailsExt:
    """Resolves the MSME virtual fields (Supplier).

    Read through the linked registration, never copied onto the Supplier, so
    they cannot drift from the MSME master.
    """

    @property
    def msme_enterprise_type(self):
        return self.get_msme_details().get("enterprise_type")

    @property
    def msme_activity(self):
        return self.get_msme_details().get("activity")

    @property
    def msme_is_cancelled(self):
        if not self.msme_registration:
            return 0

        return frappe.db.get_value("MSME Registration", self.msme_registration, "is_cancelled")

    def get_msme_details(self):
        return get_msme_classification(self.msme_registration) or {}
