# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import IfNull, IsNull


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
            [self.filters.party_type]
            if self.filters.party_type
            else ["Customer", "Supplier"]
        )

    def get_columns(self) -> list[dict]:
        """Return columns for the report.

        One field definition per column, just like a DocType field definition.
        """
        columns = [
            {
                "label": _("Party Type"),
                "fieldname": "party_type",
                "fieldtype": "Link",
                "options": "DocType",
                "width": 100,
            },
            {
                "label": _("Party Name"),
                "fieldname": "party_name",
                "fieldtype": "Dynamic Link",
                "options": "party_type",
                "width": 220,
            },
            {
                "label": _("GSTIN"),
                "fieldname": "gstin",
                "fieldtype": "Link",
                "options": "GSTIN",
                "width": 180,
            },
            {
                "label": _("Status"),
                "fieldname": "status",
                "fieldtype": "Data",
                "width": 120,
            },
            {
                "label": _("Registration Date"),
                "fieldname": "registration_date",
                "fieldtype": "Date",
                "width": 150,
            },
            {
                "label": _("Last Updated"),
                "fieldname": "last_updated_on",
                "fieldtype": "Datetime",
                "width": 150,
            },
            {
                "label": _("Cancelled Date"),
                "fieldname": "cancelled_date",
                "fieldtype": "Date",
                "width": 150,
            },
            {
                "label": _("Is Blocked"),
                "fieldname": "is_blocked",
                "fieldtype": "Data",
                "width": 80,
            },
            {
                "label": _("Update GSTIN Details"),
                "fieldname": "update_gstin_details_btn",
                "fieldtype": "Button",
                "width": 120,
            },
        ]

        return columns

    def get_data(self):
        gstin = frappe.qb.DocType("GSTIN")
        address = frappe.qb.DocType("Address")
        dynamic_link = frappe.qb.DocType("Dynamic Link")

        party_query = (
            frappe.qb.from_(address)
            .inner_join(dynamic_link)
            .on(address.name == dynamic_link.parent)
            .select(
                address.gstin,
                dynamic_link.link_doctype.as_("party_type"),
                dynamic_link.link_name.as_("party_name"),
            )
            .where(dynamic_link.link_doctype.isin(self.doctypes))
            .where(IfNull(address.gstin, "") != "")
        ).as_("party")

        for doctype in self.doctypes:
            party_query.union(get_party_query(doctype))

        gstin_query = (
            frappe.qb.from_(party_query)
            .left_join(gstin)
            .on(gstin.gstin == party_query.gstin)
            .select(
                party_query.gstin,
                gstin.status,
                gstin.registration_date,
                gstin.last_updated_on,
                gstin.cancelled_date,
                Case()
                .when(IsNull(gstin.is_blocked), "")
                .when(gstin.is_blocked == 0, "No")
                .else_("Yes")
                .as_("is_blocked"),
                party_query.party_type,
                party_query.party_name,
            )
            .orderby(gstin.modified, order=Order.desc)
        )

        if self.filters.status:
            gstin_query = gstin_query.where(gstin.status == self.filters.status)

        return gstin_query.run(as_dict=True)


def get_party_query(doctype):
    dt = frappe.qb.DocType(doctype)

    query = (
        frappe.qb.from_(dt)
        .select(
            dt.gstin,
            dt.doctype.as_("party_type"),
            dt.name.as_("party_name"),
        )
        .where(IfNull(dt.gstin, "") != "")
    )

    return query
