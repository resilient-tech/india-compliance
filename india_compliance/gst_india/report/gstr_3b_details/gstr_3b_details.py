# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_first_day, get_last_day

from india_compliance.gst_india.utils import get_period
from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import (
    INWARD_SECTION_SUB_CATEGORY_MAP,
    GSTR3BInwardInvoices,
)


def execute(filters=None):

    validate_filters(filters)

    report = BaseGSTR3BDetails(filters)

    return report.run()


def validate_filters(filters):
    filters = frappe._dict(filters)
    section = cstr(filters.section)

    if not section:
        frappe.throw(_("Please select a section to view details"))

    if section not in INWARD_SECTION_SUB_CATEGORY_MAP.keys():
        frappe.throw(_("Invalid section selected"))


class BaseGSTR3BDetails:
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.company_currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")
        self.month_or_quarter_no = get_period(self.filters.month_or_quarter)
        self.from_date = get_first_day(f"{cint(self.filters.year)}-{self.month_or_quarter_no[0]}-01")
        self.to_date = get_last_day(f"{cint(self.filters.year)}-{self.month_or_quarter_no[1]}-01")
        self.company = self.filters.company
        self.company_gstin = self.filters.company_gstin
        self.filter_by = self.filters.filter_by or "ITC Claim Period"
        self.section = cstr(self.filters.section)

    def run(self):
        if self.section not in INWARD_SECTION_SUB_CATEGORY_MAP.keys():
            frappe.throw(_("Invalid section selected"))

        data = self.get_data()
        columns = self.get_columns()

        return columns, data

    def get_inward_filters(self):
        return frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
                "from_date": self.from_date,
                "to_date": self.to_date,
                "filter_by": self.filter_by,
            }
        )

    def get_filtered_inward_data(self):
        return GSTR3BInwardInvoices(self.get_inward_filters()).get_section_data(
            self.section, group_by_invoice=True
        )

    def get_data(self):
        return sorted(
            self.get_filtered_inward_data(),
            key=lambda row: (row["invoice_sub_category"], row["posting_date"]),
        )

    def get_columns(self):
        columns = [
            {
                "fieldname": "voucher_type",
                "label": _("Voucher Type"),
                "fieldtype": "Data",
                "width": 100,
            },
            {
                "fieldname": "voucher_no",
                "label": _("Voucher No"),
                "fieldtype": "Dynamic Link",
                "options": "voucher_type",
            },
            {
                "fieldname": "posting_date",
                "label": _("Posting Date"),
                "fieldtype": "Date",
                "width": 100,
            },
        ]

        if self.section == "4":
            columns.extend(self.get_section_4_columns())
        elif self.section == "5":
            columns.extend(self.get_section_5_columns())

        return columns

    def get_section_4_columns(self):
        return [
            {
                "fieldname": "igst_amount",
                "label": _("Integrated Tax"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 100,
            },
            {
                "fieldname": "cgst_amount",
                "label": _("Central Tax"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 100,
            },
            {
                "fieldname": "sgst_amount",
                "label": _("State/UT Tax"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 100,
            },
            {
                "fieldname": "cess_amount",
                "label": _("Cess Tax"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 100,
            },
            {
                "fieldname": "invoice_sub_category",
                "label": _("Eligibility for ITC"),
                "fieldtype": "Data",
                "width": 100,
            },
        ]

    def get_section_5_columns(self):
        return [
            {
                "fieldname": "intra",
                "label": _("Intra State"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 100,
            },
            {
                "fieldname": "inter",
                "label": _("Inter State"),
                "fieldtype": "Currency",
                "options": self.company_currency,
                "width": 100,
            },
            {
                "fieldname": "invoice_sub_category",
                "label": _("Nature of Supply"),
                "fieldtype": "Data",
                "width": 100,
            },
        ]
