from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
    get_columns,
    process_hsn_data,
    validate_filters,
)
from india_compliance.gst_india.utils.gstr3b.gstr3b_data import GSTR3BInvoices


def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def get_data(filters):
    _class = GSTR3BInvoices(filters)
    invoices = []

    for doctype in ("Purchase Invoice", "Bill of Entry"):
        invoices.extend(_class.get_data(doctype))

    return process_hsn_data(invoices)
