import frappe

from india_compliance.gst_india.overrides.company import SINGLE_DOCTYPES_WITH_COMPANY_FIELD


def execute():
    for doctype in SINGLE_DOCTYPES_WITH_COMPANY_FIELD:
        frappe.db.set_single_value(doctype, {"company": None, "company_gstin": None})
