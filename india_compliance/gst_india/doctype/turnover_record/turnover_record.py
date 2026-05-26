# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from india_compliance.gst_india.utils import get_state, validate_gst_category, validate_gstin

# TODO: remove gst category from turnover records 

class TurnoverRecord(Document):
    def autoname(self):
        self.name = f"{self.fiscal_year}-{self.gst_state}"

    def validate(self):
        validate_gstin(self.gstin)
        if self.gstin and get_state(self.gstin[:2]) != self.gst_state:
            # for registered company, gstin and gst state are compulsory and validated
            frappe.throw(_("GSTIN does not match selected state"))


def upsert_turnover_record(
    gstin,
    gst_state,
    fiscal_year,
    amount,
):

    filters = {"fiscal_year": fiscal_year}
    or_filters = {"gst_state": gst_state, "gstin": gstin or ""}

    existing = frappe.db.get_list(
        "Turnover Record", filters=filters, or_filters=or_filters, pluck="name", limit=1
    )
    existing = existing[0] if existing else None

    try:
        if existing:
            frappe.db.set_value("Turnover Record", existing, "amount", amount)
        else:
            doc = frappe.new_doc("Turnover Record")
            doc.fiscal_year = fiscal_year
            doc.gstin = gstin
            doc.gst_state = gst_state
            doc.amount = amount
            doc.insert(ignore_permissions=True)
    except frappe.ValidationError:
        frappe.log_error(
            title=_("Turnover Record upsert failed"),
            message=_(
                "Failed to upsert Turnover Record for fiscal_year={0}, gst_state={1}, gstin={2}"
            ).format(fiscal_year, gst_state, gstin),
        )
