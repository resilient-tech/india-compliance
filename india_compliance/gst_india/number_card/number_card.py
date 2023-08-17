import frappe
from frappe.utils import add_months, getdate
import erpnext

from india_compliance.gst_india.report.e_invoice_summary.e_invoice_summary import (
    get_data,
)


@frappe.whitelist()
def get_pending_e_invoices_count():
    if not frappe.has_permission("Sales Invoice"):
        return 0

    last_quarter_date = add_months(getdate(), -3)
    filters = {
        "company": erpnext.get_default_company(),
        "exceptions": "e-Invoice Not Generated",
        "from_date": last_quarter_date,
        "to_date": getdate(),
    }

    return get_e_invoice_summary_count(filters)


@frappe.whitelist()
def get_active_e_invoice_count_for_cancelled_invoices():
    if not frappe.has_permission("Sales Invoice"):
        return 0

    last_quarter_date = add_months(getdate(), -3)
    filters = {
        "company": erpnext.get_default_company(),
        "exceptions": "Invoice Cancelled but not e-Invoice",
        "from_date": last_quarter_date,
        "to_date": getdate(),
    }

    return get_e_invoice_summary_count(filters)


def get_e_invoice_summary_count(filters):
    e_invoice_summary = get_data(filters)

    return {
        "value": len(e_invoice_summary),
        "fieldtype": "Int",
        "route_options": filters,
        "route": ["query-report", "e-Invoice Summary"],
    }
