import frappe
from frappe.utils import add_months, getdate

from india_compliance.gst_india.report.e_invoice_summary.e_invoice_summary import (
    get_data_for_all_companies,
)


@frappe.whitelist()
def get_pending_e_invoices_count(filters=None):
    if not frappe.has_permission("Sales Invoice"):
        return 0

    if not filters:
        filters = {}

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)

    last_quarter_date = add_months(getdate(), -3)

    default_filters = frappe._dict(
        {
            "exceptions": "e-Invoice Not Generated",
            "from_date": last_quarter_date,
            "to_date": getdate(),
        }
    )

    if filters.get("company"):
        default_filters["company"] = filters.get("company")

    return get_e_invoice_summary_count(default_filters)


@frappe.whitelist()
def get_active_e_invoice_count_for_cancelled_invoices(filters=None):
    if not frappe.has_permission("Sales Invoice"):
        return 0

    if not filters:
        filters = {}

    if isinstance(filters, str):
        filters = frappe.json.loads(filters)

    last_quarter_date = add_months(getdate(), -3)
    default_filters = frappe._dict(
        {
            "exceptions": "Invoice Cancelled but not e-Invoice",
            "from_date": last_quarter_date,
            "to_date": getdate(),
        }
    )
    if filters.get("company"):
        default_filters["company"] = filters.get("company")

    return get_e_invoice_summary_count(default_filters)


def get_e_invoice_summary_count(filters):
    e_invoice_summary = get_data_for_all_companies(filters)

    return {
        "value": len(e_invoice_summary),
        "fieldtype": "Int",
        "route_options": filters,
        "route": ["query-report", "e-Invoice Summary"],
    }
