# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from india_compliance.gst_india.utils import get_state, validate_gst_category, validate_gstin


class TurnoverRecord(Document):
    def autoname(self):
        self.name = f"{self.fiscal_year}-{self.gst_state}"

    def validate(self):
        validate_gstin(self.gstin)
        validate_gst_category(self.gst_category, self.gstin)
        if self.gstin and get_state(self.gstin[:2]) != self.gst_state:
            # for registered company, gstin and gst state are compulsory and validated
            frappe.throw(_("GSTIN does not match selected state"))


def upsert_turnover_record(
    gstin,
    gst_category,
    gst_state,
    fiscal_year,
    amount,
):

    filters = {"fiscal_year": fiscal_year}
    or_filters = {"gst_state": gst_state, "gstin": gstin or ""}

    existing = frappe.db.get_list("Turnover Record", filters=filters, or_filters=or_filters, pluck="name", limit=1)
    existing = existing[0] if existing else None

    try:
        if existing:
            frappe.db.set_value("Turnover Record", existing, "amount", amount)
        else:
            doc = frappe.new_doc("Turnover Record")
            doc.fiscal_year = fiscal_year
            doc.gstin = gstin
            doc.gst_state = gst_state
            doc.gst_category = gst_category
            doc.amount = amount
            doc.insert(ignore_permissions=True)
    except frappe.ValidationError as e:
        return
