from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    get_columns,
    process_hsn_data,
    validate_filters,
)
from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import GSTR3BInwardInvoices

# GSTR-3B repeats an ineligible invoice under this category to reverse its ITC
ITC_REVERSED = "ITC Reversed"


def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def get_data(filters):
    inward_invoices = GSTR3BInwardInvoices(filters)
    invoices = []

    for doctype in ("Purchase Invoice", "Bill of Entry"):
        invoices.extend(
            invoice
            for invoice in inward_invoices.get_data(doctype)
            if invoice.invoice_category != ITC_REVERSED
        )

    return process_hsn_data(invoices)
