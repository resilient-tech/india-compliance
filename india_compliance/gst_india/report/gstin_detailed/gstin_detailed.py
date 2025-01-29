# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
import frappe.query_builder
from frappe import _


def execute(filters: dict | None = None):
    """Return columns and data for the report.

    This is the main entry point for the report. It accepts the filters as a
    dictionary and should return columns and data. It is called by the framework
    every time the report is refreshed or a filter is updated.
    """
    report = GSTINDetailedReport(filters=filters)
    columns = report.get_columns()
    data = report.get_data()

    return columns, data


class GSTINDetailedReport:

    def __init__(self, filters: dict | None = None):
        self.filters = frappe._dict(filters or {})
        self.doctypes = (
            [self.filters.reference_party]
            if self.filters.reference_party != "All"
            else ["Customer", "Supplier"]
        )
        print("Doctypes", self.doctypes)
        self.gstin_fields = [
            "gstin",
            "status",
            "registration_date",
            "last_updated_on",
            "cancelled_date",
            "is_blocked",
        ]

    def get_columns(self) -> list[dict]:
        """Return columns for the report.

        One field definition per column, just like a DocType field definition.
        """
        columns = [
            {
                "label": _("GSTIN"),
                "fieldname": "gstin",
                "fieldtype": "Data",
            },
            {
                "label": _("Status"),
                "fieldname": "status",
                "fieldtype": "Data",
            },
            {
                "label": _("Registration Date"),
                "fieldname": "registration_date",
                "fieldtype": "Date",
            },
            {
                "label": _("Last Updated On"),
                "fieldname": "last_updated_on",
                "fieldtype": "Date",
            },
            {
                "label": _("Cancelled Date"),
                "fieldname": "cancelled_date",
                "fieldtype": "Date",
            },
            {
                "label": _("Is Blocked"),
                "fieldname": "is_blocked",
                "fieldtype": "Data",
            },
            {
                "label": _("Reference Party"),
                "fieldname": "reference_party",
                "fieldtype": "Data",
            },
            {
                "label": _("Party Name"),
                "fieldname": "party_name",
                "fieldtype": "Data",
            },
            {
                "label": _("Update GSTIN Details"),
                "fieldname": "update_gstin_details_btn",
                "fieldtype": "Button",
                "width": 160,
            },
        ]

        return columns

    def get_data(self) -> list[list]:
        """Return data for the report.

        The report data is a list of rows, with each row being a list of cell values.
        """
        all_references = self.get_all_references()
        reference_gstins = [reference[0] for reference in all_references]
        gstins_details = self.get_all_gstins_details(reference_gstins)

        all_references = list(
            filter(lambda reference: reference[0] in gstins_details, all_references)
        )
        rows = self.convert_to_rows(
            all_references=all_references, gstins_details=gstins_details
        )
        rows.sort(key=lambda row: row[-1], reverse=True)
        return rows

    def get_all_gstins_details(self, gstins):
        filters = {"name": ["in", gstins]}

        if self.filters.status != "All":
            filters["status"] = self.filters.status

        gstins_details = frappe.get_list(
            "GSTIN", filters=filters, fields=[*self.gstin_fields, "modified"]
        )

        return {detail.gstin: detail for detail in gstins_details}

    def get_all_references(self):
        all_references = set()
        for doctype in self.doctypes:
            reference = frappe.get_list(
                doctype=doctype,
                filters={"gstin": ["is", "set"]},
                fields=["name", "gstin"],
            )

            all_references.update(
                [(detail.gstin, doctype, detail.name) for detail in reference]
            )

        Address = frappe.qb.DocType("Address")
        DynamicLink = frappe.qb.DocType("Dynamic Link")

        query = (
            frappe.qb.from_(Address)
            .inner_join(DynamicLink)
            .on(Address.name == DynamicLink.parent)
            .select(Address.gstin, DynamicLink.link_doctype, DynamicLink.link_name)
            .where(DynamicLink.link_doctype.isin(self.doctypes))
        )

        address_references = query.run()
        all_references.update(address_references)
        return all_references

    def convert_to_rows(self, all_references, gstins_details):
        rows = []

        for reference in all_references:
            gstin = reference[0]
            status = gstins_details[gstin]["status"]
            registration_date = gstins_details[gstin]["registration_date"]
            last_updated_on = gstins_details[gstin]["last_updated_on"]
            cancelled_date = gstins_details[gstin]["cancelled_date"]
            is_blocked = "Yes" if gstins_details[gstin]["is_blocked"] else "No"
            reference_party = reference[1]
            party_name = reference[2]
            modified = gstins_details[gstin]["modified"]

            row = [
                gstin,
                status,
                registration_date,
                last_updated_on,
                cancelled_date,
                is_blocked,
                reference_party,
                party_name,
                "Update",
                modified,
            ]

            rows.append(row)

        return rows
