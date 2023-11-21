# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.data import format_datetime, get_timespan_date_range, getdate

from india_compliance.audit_trail.utils import get_audit_trail_doctypes

FIELDS = {
    "supplier_name_field_doctypes": [
        "Purchase Invoice",
        "Purchase Receipt",
        "Stock Entry",
        "Subcontracting Receipt",
    ],
    "customer_name_field_doctypes": [
        "POS Invoice",
        "Dunning",
        "Sales Invoice",
        "Delivery Note",
    ],
    "no_name_field_doctypes": [
        "Account Settings",
        "Period Closing Voucher",
        "Process Deferred Accounting",
        "Asset",
        "Asset Repair",
        "Landed Cost Voucher",
    ],
    "grand_total_field_doctypes": [
        "Dunning",
        "Purchase Invoice",
        "Sales Invoice",
        "Delivery Note",
        "Purchase Receipt",
        "POS Invoice",
    ],
    "total_amount_field_doctypes": [
        "Stock Entry",
        "Invoice Discounting",
        "Journal Entry",
    ],
    "remarks_field_doctypes": [
        "Purchase Invoice",
        "Purchase Receipt",
        "Stock Entry",
        "Subcontracting Receipt",
        "Payment Entry",
        "Sales Invoice",
        "POS Invoice",
        "Period Closing Voucher",
    ],
}


def execute(filters=None):
    _class = REPORT_MAP[filters.pop("report")](filters)
    return _class.get_columns(), _class.get_data()


class BaseAuditTrail:
    def __init__(self, filters) -> None:
        self.filters = filters

    def get_columns(self):
        pass

    def get_data(self):
        pass

    def append_rows(self, new_count, modified_count, doctype):
        pass

    def get_conditions(self):
        conditions = {}
        conditions["modified"] = self.get_date()
        conditions["owner"] = self.get_user()
        conditions["company"] = self.filters.get("company")

        return conditions

    def get_date(self):
        date_option = self.filters.pop("date_option", None)
        date_range = self.filters.pop("date_range", None)
        if date_option == "Custom":
            return ["between", date_range]
        else:
            date_range = [get_timespan_date_range(date_option.lower())][0]
            return ("between", date_range)

    def get_user(self):
        if self.filters.get("user"):
            return self.filters["user"]

        else:
            users = frappe.get_all("User", pluck="name")
            return ["in", users]

    def get_doctypes(self):
        doctypes = list(get_relavant_doctypes())
        return doctypes

    def update_count(self):
        fields = ["owner as user_name", "count(name) as count"]
        self.filters["creation"] = self.get_date()

        if doctype := self.filters.pop("doctype", None):
            doctypes = [doctype]
        else:
            doctypes = self.get_doctypes()

        if user := self.filters.pop("user", None):
            self.filters["owner"] = user

        # Removed Company Filter for 'modified_count' Due to Versioning Not Being Maintained on a Company Basis
        filters = self.filters.copy()
        del filters["company"]

        for doctype in doctypes:
            new_count = frappe.get_all(
                doctype,
                filters=self.filters,
                fields=fields,
                group_by=self.group_by,
            )

            modified_count = frappe.get_all(
                "Version",
                filters={**filters, "ref_doctype": doctype},
                fields=fields,
                group_by=self.group_by,
            )

            self.append_rows(new_count, modified_count, doctype)


class DetailedReport(BaseAuditTrail):
    def get_columns(self):
        columns = [
            {
                "label": _("Date and Time"),
                "fieldtype": "DateTime",
                "fieldname": "date_time",
                "width": 160,
            },
            {
                "label": _("DocType"),
                "fieldtype": "Link",
                "fieldname": "doctype",
                "options": "DocType",
                "width": 120,
            },
            {
                "label": _("Document Name"),
                "fieldtype": "Dynamic Link",
                "fieldname": "document_name",
                "width": 150,
                "options": "doctype",
            },
            {
                "label": _("Creation Date"),
                "fieldtype": "Date",
                "fieldname": "creation_date",
                "width": 120,
            },
            {
                "label": _("Party Type"),
                "fieldtype": "Link",
                "fieldname": "party_type",
                "width": 100,
                "options": "DocType",
            },
            {
                "label": _("Party Name"),
                "fieldtype": "Dynamic Link",
                "fieldname": "party_name",
                "width": 150,
                "options": "party_type",
            },
            {
                "label": _("Amount"),
                "fieldtype": "Int",
                "fieldname": "amount",
                "width": 80,
            },
            {
                "label": _("Created By"),
                "fieldtype": "Link",
                "fieldname": "created_by",
                "options": "User",
                "width": 150,
            },
            {
                "label": _("Modified By"),
                "fieldtype": "Link",
                "fieldname": "modified_by",
                "options": "User",
                "width": 150,
            },
            {
                "label": _("Remarks"),
                "fieldtype": "Data",
                "fieldname": "remarks",
                "width": 180,
            },
        ]

        return columns

    def get_data(self):
        self.data = []
        conditions = self.get_conditions()

        if doctype := self.filters.get("doctype"):
            doctypes = [doctype]
        else:
            doctypes = self.get_doctypes()

        for doctype in doctypes:
            fields = self.get_fields(doctype)
            records = frappe.get_all(doctype, fields=fields, filters=conditions)
            self.append_rows(records, doctype)

        return self.data

    def get_fields(self, doctype):
        fields = [
            "modified as date_time",
            "company",
            "name as document_name",
            "owner as created_by",
            "modified_by as modified_by",
        ]

        if doctype == "Payment Entry":
            fields.extend(
                ["party_type", "party_name", "total_allocated_amount as amount"]
            )

        # Amount
        if doctype == "Subcontracting Receipt":
            fields.append("total as amount")

        elif doctype == "Bill of Entry":
            fields.append("total_amount_payable as amount")

        elif doctype in FIELDS["grand_total_field_doctypes"]:
            fields.append("grand_total as amount")

        elif doctype in FIELDS["total_amount_field_doctypes"]:
            fields.append("total_amount as amount")

        # Party Name
        if doctype in FIELDS["supplier_name_field_doctypes"]:
            fields.append("supplier_name as party_name")

        elif doctype in FIELDS["customer_name_field_doctypes"]:
            fields.append("customer_name as party_name")

        # Remarks
        if doctype == "Journal Entry":
            fields.append("user_remark as remarks")

        elif doctype in FIELDS["remarks_field_doctypes"]:
            fields.append("remarks")

        return fields

    def append_rows(self, records, doctype):
        for row in records:
            row["date_time"] = format_datetime(row["date_time"])
            row["doctype"] = doctype
            row["creation_date"] = getdate(row["date_time"])

            if doctype == "Bill of Entry":
                row["party_name"] = ""

            elif doctype in FIELDS["no_name_field_doctypes"]:
                row["party_name"] = ""
                row["amount"] = ""

            elif doctype in FIELDS["supplier_name_field_doctypes"]:
                row["party_type"] = "Supplier"

            elif doctype in FIELDS["customer_name_field_doctypes"]:
                row["party_type"] = "Customer"

            self.data.append(row)


class DocTypeReport(BaseAuditTrail):
    def get_columns(self):
        columns = [
            {
                "label": _("DocType"),
                "fieldtype": "Link",
                "fieldname": "doctype",
                "options": "DocType",
                "width": 150,
            },
            {
                "label": _("New Records"),
                "fieldtype": "Data",
                "fieldname": "new_count",
                "width": 150,
            },
            {
                "label": _("Modified Records"),
                "fieldtype": "Data",
                "fieldname": "modify_count",
                "width": 150,
            },
        ]

        return columns

    def get_data(self):
        self.data = {}
        self.group_by = ""
        self.update_count()

        return list(self.data.values())

    def append_rows(self, new_records, modified_records, doctype):
        new_count = modify_count = 0
        for row in new_records:
            new_count += row["count"]

        for row in modified_records:
            modify_count += row["count"]

        if not (new_count or modify_count):
            return

        row = {"doctype": doctype, "new_count": new_count, "modify_count": modify_count}
        self.data.setdefault(doctype, row)


class UserReport(BaseAuditTrail):
    def get_columns(self):
        columns = [
            {
                "label": _("User"),
                "fieldtype": "Link",
                "fieldname": "user_name",
                "options": "User",
                "width": 200,
            },
            {
                "label": _("New Records"),
                "fieldtype": "Data",
                "fieldname": "new_count",
                "width": 150,
            },
            {
                "label": _("Modified Records"),
                "fieldtype": "Data",
                "fieldname": "modify_count",
                "width": 150,
            },
        ]

        return columns

    def get_data(self):
        self.data = {}
        self.group_by = "owner"
        self.update_count()

        return list(self.data.values())

    def append_rows(self, new_records, modified_records, doctype):
        for row in new_records:
            user_name = row["user_name"]
            user_count = self.data.setdefault(
                user_name,
                {
                    "user_name": user_name,
                    "new_count": 0,
                    "modify_count": 0,
                },
            )

            user_count["new_count"] += row["count"]

        for row in modified_records:
            user_name = row["user_name"]
            user_count = self.data.setdefault(
                user_name,
                {
                    "user_name": user_name,
                    "new_count": 0,
                    "modify_count": 0,
                },
            )

            user_count["modify_count"] += row["count"]


@frappe.whitelist()
def get_relavant_doctypes():
    doctypes = get_audit_trail_doctypes()
    doctypes.remove("Accounts Settings")

    if frappe.get_cached_value(
        "Accounts Settings",
        "Accounts Settings",
        "automatically_process_deferred_accounting_entry",
    ):
        doctypes.remove("Process Deferred Accounting")

    return doctypes


REPORT_MAP = {
    "Detailed": DetailedReport,
    "Summary by DocType": DocTypeReport,
    "Summary by User": UserReport,
}
