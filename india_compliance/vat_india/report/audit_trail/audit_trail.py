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

    _class = REPORT_MAP[filters.get("report")]()
    filters.pop("report")

    return _class.get_columns(), _class.get_data(filters)


class DetailedReport:
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
                "fieldtype": "link",
                "fieldname": "company",
                "options": "Company",
                "width": 150,
            },
            {
                "label": _("Doctype"),
                "fieldtype": "link",
                "fieldname": "doctype",
                "options": "Doctype",
                "width": 150,
            },
            {
                "label": _("Document Name"),
                "fieldtype": "data",
                "fieldname": "document_name",
                "width": 150,
            },
            {
                "label": _("Creation Date"),
                "fieldtype": "date",
                "fieldname": "creation_date",
                "width": 150,
            },
            {
                "label": _("Party Name/Remarks"),
                "fieldtype": "data",
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
                "fieldtype": "data",
                "fieldname": "created_by",
                "width": 200,
            },
            {
                "label": _("Modified By"),
                "fieldtype": "data",
                "fieldname": "modified_by",
                "width": 200,
            },
        ]

        return columns

    def get_data(self, filters):
        data = []
        conditions = get_conditions(filters)
        print(conditions)

        if doctype := filters.get("doctype"):
            doctypes = [doctype]
        else:
            doctypes = get_doctypes()

        for doctype in doctypes:
            fields = self.get_fields(doctype)
            records = frappe.db.get_all(doctype, fields=fields, filters=conditions)
            data = self.get_rows(records, doctype, data)
        return data

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

    def get_rows(self, records, doctype, data):

        for row in records:
            row["date_time"] = format_datetime(row["date_time"])
            row["doctype"] = doctype
            row["creation_date"] = getdate(row["date_time"])

            if doctype == "Bill of Entry":
                row["party_name"] = ""
            elif doctype in FIELDS["no_name_field_doctypes"]:
                row["party_name"] = ""
                row["party_amount"] = ""

            data.append(row)

        return data


class DoctypeReport:
    def get_columns(self):
        columns = [
            {
                "label": _("Doctype"),
                "fieldtype": "data",
                "fieldname": "doctype",
                "width": 150,
            },
            {
                "label": _("New Records"),
                "fieldtype": "data",
                "fieldname": "new_record",
                "width": 120,
            },
            {
                "label": _("Modify"),
                "fieldtype": "data",
                "fieldname": "modify",
                "width": 80,
            },
        ]

        return columns

    def get_data(self, filters):
        data = []
        data = get_count(filters, data, report="doctype")
        return data

    def get_rows(self, new_count, modified_count, doctype, data):
        new_record = modify = 0
        for n in new_count:
            new_record += n["count"]
        for m in modified_count:
            modify += m["count"]

        if new_record != 0:
            row = {"doctype": doctype, "new_record": new_record, "modify": modify}
            data.append(row)
        return data


class UserReport:
    def get_columns(self):
        columns = [
            {
                "label": _("User Name"),
                "fieldtype": "data",
                "fieldname": "user_name",
                "width": 200,
            },
            {
                "label": _("New Records"),
                "fieldtype": "data",
                "fieldname": "count",
                "width": 120,
            },
            {
                "label": _("Modify"),
                "fieldtype": "data",
                "fieldname": "modify",
                "width": 80,
            },
        ]

        return columns

    def get_data(self, filters):
        data = []
        data = get_count(filters, data, report="user")

        return data

    def get_rows(self, new_count, modified_count, data):
        if not data:
            for row in new_count:
                row["modify"] = 0
                data.append(row)
        else:
            for row in new_count:
                owner_matched = False

                for d in data:
                    if row["user_name"] == d["user_name"]:
                        d["count"] += row["count"]
                        owner_matched = True
                        break

                if not owner_matched:
                    row["modify"] = 0
                    data.append(row)

        for m in modified_count:
            for d in data:
                if m["user_name"] == d["user_name"]:
                    d["modify"] += m["count"]
                    break
        return data


REPORT_MAP = {
    "Detailed": DetailedReport,
    "Summary by Doctype": DoctypeReport,
    "Summary by User": UserReport,
}


##################### Utils ###############################


def get_conditions(filters):
    conditions = {}
    conditions["modified"] = get_date(filters)
    conditions["owner"] = get_user(filters)

    return conditions


def get_date(filters):

    if filters["date"] == "Custom":
        return ["between", [filters["date_range"][0], filters["date_range"][1]]]
    elif filters["date"] == "Today" or filters["date"] == "Yesterday":
        date = [get_timespan_date_range(filters["date"].lower())][0]
        return ("like", f"{date[0]}%")
    else:
        date = [get_timespan_date_range(filters["date"].lower())][0]
        return ("between", [date[0], date[1]])


def get_user(filters):

    if filters.get("user"):
        return filters["user"]

    else:
        users = frappe.db.get_all("User", fields=["name"])
        return ["in", (user.name for user in users)]


def get_doctypes():
    doctypes = list(get_audit_trail_doctypes())
    doctypes.remove("Accounts Settings")
    return doctypes


def get_count(filters, data, report):
    group_by = "owner"
    fields = ["owner as user_name", "count(name) as count"]
    if doctype := filters.get("doctype"):
        doctypes = [doctype]
    else:
        doctypes = get_doctypes()

    filters.pop("doctype", None)
    filters["creation"] = get_date(filters)
    filters.pop("date")
    if filters.get("user", None):
        filters["owner"] = filters.pop("user")
        group_by = ""

    for doctype in doctypes:
        new_count = frappe.db.get_all(
            doctype, filters=filters, fields=fields, group_by=group_by
        )
        modified_count = frappe.db.get_all(
            "Version",
            filters={**filters, "ref_doctype": doctype},
            fields=fields,
            group_by=group_by,
        )

        if report == "doctype":
            data = DoctypeReport().get_rows(new_count, modified_count, doctype, data)
        if report == "user" and (new_count and new_count[0]["user_name"]):
            data = UserReport().get_rows(new_count, modified_count, data)

    return data
