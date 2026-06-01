# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.accounts.report.purchase_register.purchase_register import _execute
from frappe import _

<<<<<<< HEAD

def execute(filters=None):
    return _execute(filters, get_additional_table_columns())

=======
from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import (
    INWARD_SECTION_SUB_CATEGORY_MAP,
    GSTR3BInwardInvoices,
)
>>>>>>> fab7eb8c (refactor: gstr3b data)

def get_additional_table_columns():
    return [
        {
            "fieldtype": "Data",
            "label": _("Supplier GSTIN"),
            "fieldname": "supplier_gstin",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("Company GSTIN"),
            "fieldname": "company_gstin",
            "width": 120,
        },
        {
            "fieldtype": "Check",
            "label": _("Is Reverse Charge"),
            "fieldname": "is_reverse_charge",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("GST Category"),
            "fieldname": "gst_category",
            "width": 120,
        },
    ]
<<<<<<< HEAD
=======


def get_data(filters):
    gstr3b_invoices = GSTR3BInwardInvoices(filters)
    is_grouped_by_invoice = filters.summary_by != "Summary by Item"
    sub_section = filters.sub_section

    # Set default invoice sub categories if only sub_section is selected
    if not filters.invoice_sub_category:
        filters.invoice_sub_category = get_invoice_sub_categories(sub_section)

    data = gstr3b_invoices.get_section_data(
        sub_section,
        group_by_invoice=is_grouped_by_invoice,
        invoice_sub_categories=filters.invoice_sub_category,
    )

    if filters.summary_by == "Overview":
        return get_summary_view(data, sub_section)

    data = sorted(data, key=lambda k: (k["invoice_sub_category"], k["posting_date"]))

    return data


def get_invoice_sub_categories(sub_section):
    return GSTR3BInwardInvoices.get_section_sub_categories(sub_section)


def get_summary_view(data, sub_section):
    mapping = INWARD_SECTION_SUB_CATEGORY_MAP[sub_section]
    amount_fields = AMOUNT_FIELDS_MAP[sub_section]

    final_summary = []
    sub_category_summary = get_sub_category_summary(data, mapping, amount_fields)

    for category, sub_categories in mapping.items():
        if category == "Ineligible ITC" and sub_section == "4":
            add_net_itc_row(final_summary, amount_fields)

        category_summary = {
            "description": category,
            "no_of_records": 0,
            "indent": 0,
            **amount_fields,
        }
        final_summary.append(category_summary)

        for sub_category in sub_categories:
            sub_category_row = sub_category_summary[sub_category]
            category_summary["no_of_records"] += sub_category_row["no_of_records"]

            for key in amount_fields:
                category_summary[key] += sub_category_row[key]

            final_summary.append(sub_category_row)

    return final_summary


def add_net_itc_row(summary, amount_fields):
    row = {
        "description": "Net ITC Available",
        "no_of_records": 0,
        "indent": 0,
        **amount_fields,
    }

    for summary_row in summary:
        if summary_row["description"] == "ITC Available":
            for key in amount_fields:
                row[key] += summary_row[key]
            row["no_of_records"] += summary_row["no_of_records"]

        elif summary_row["description"] == "ITC Reversed":
            for key in amount_fields:
                row[key] -= summary_row[key]
            row["no_of_records"] -= summary_row["no_of_records"]

    summary.append(row)


def get_sub_category_summary(data, mapping, amount_fields):
    sub_categories = []
    for category in mapping:
        sub_categories.extend(mapping[category])

    summary = {
        category: {
            "description": category,
            "no_of_records": 0,
            "indent": 1,
            "unique_records": set(),
            **amount_fields,
        }
        for category in sub_categories
    }

    def _update_summary_row(row):
        if row.get("invoice_sub_category") not in sub_categories:
            return

        summary_row = summary[row.get("invoice_sub_category")]

        for key in amount_fields:
            summary_row[key] += row[key]

        summary_row["unique_records"].add(row["voucher_no"])

    for row in data:
        _update_summary_row(row)

    for summary_row in summary.values():
        summary_row["no_of_records"] = len(summary_row["unique_records"])

    return summary
>>>>>>> fab7eb8c (refactor: gstr3b data)
