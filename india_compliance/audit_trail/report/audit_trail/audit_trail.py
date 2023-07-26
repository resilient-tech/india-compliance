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

    def append_rows(self):
        pass

    def get_conditions(self):
        conditions = {}
        conditions["modified"] = self.get_date()
        conditions["owner"] = self.get_user()

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
        doctypes = list(self.get_audit_trail_doctypes())
        doctypes.remove("Accounts Settings")
        return doctypes

    def get_audit_trail_doctypes(self):
        return get_audit_trail_doctypes()

    def update_count(self):
        fields = ["owner as user_name", "count(name) as count"]
        self.filters["creation"] = self.get_date()

        if doctype := self.filters.pop("doctype", None):
            doctypes = [doctype]
        else:
            doctypes = self.get_doctypes()

        if user := self.filters.pop("user", None):
            self.filters["owner"] = user

        for doctype in doctypes:
            new_count = frappe.get_all(
                doctype,
                filters=self.filters,
                fields=fields,
                group_by=self.group_by,
            )

            modified_count = frappe.get_all(
                "Version",
                filters={**self.filters, "ref_doctype": doctype},
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
                "width": 200,
            },
            {
                "label": _("Company"),
                "fieldtype": "Link",
                "fieldname": "company",
                "options": "Company",
                "width": 150,
            },
            {
                "label": _("DocType"),
                "fieldtype": "Link",
                "fieldname": "doctype",
                "options": "DocType",
                "width": 150,
            },
            {
                "label": _("Document Name"),
                "fieldtype": "Data",
                "fieldname": "document_name",
                "width": 150,
            },
            {
                "label": _("Creation Date"),
                "fieldtype": "Date",
                "fieldname": "creation_date",
                "width": 150,
            },
            {
                "label": _("Party Name/Remarks"),
                "fieldtype": "Data",
                "fieldname": "party_name",
                "width": 180,
            },
            {
                "label": _("Amount"),
                "fieldtype": "Int",
                "fieldname": "amount",
                "width": 80,
            },
            {
                "label": _("Created By"),
                "fieldtype": "Data",
                "fieldname": "created_by",
                "width": 200,
            },
            {
                "label": _("Modified By"),
                "fieldtype": "Data",
                "fieldname": "modified_by",
                "width": 200,
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
            fields.extend(["party_name", "total_allocated_amount as amount"])

        if doctype == "Subcontracting Receipt":
            fields.append("total as amount")

        if doctype == "Bill of Entry":
            fields.append("total_amount_payable as amount")

        if doctype in FIELDS["supplier_name_field_doctypes"]:
            fields.append("supplier_name as party_name")

        if doctype in FIELDS["customer_name_field_doctypes"]:
            fields.append("customer_name as party_name")

        if doctype in FIELDS["no_name_field_doctypes"]:
            return fields

        if doctype in FIELDS["grand_total_field_doctypes"]:
            fields.append("grand_total as amount")

        if doctype in FIELDS["total_amount_field_doctypes"]:
            fields.append("total_amount as amount")

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
                row["party_amount"] = ""

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


REPORT_MAP = {
    "Detailed": DetailedReport,
    "Summary by DocType": DocTypeReport,
    "Summary by User": UserReport,
}
