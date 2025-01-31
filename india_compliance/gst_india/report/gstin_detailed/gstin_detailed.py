# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
import frappe.query_builder
from frappe import _
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import Function

from india_compliance.gst_india.doctype.gstin.gstin import create_or_update_gstin_status


def DATE_FORMAT(field, format_str="%Y-%m-%d"):
    return Function("DATE_FORMAT", field, format_str)


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
                "label": _("GSTIN"),
                "fieldname": "gstin",
                "fieldtype": "Link",
                "options": "GSTIN",
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
                "label": _("Party Type"),
                "fieldname": "party_type",
                "fieldtype": "Link",
                "options": "DocType",
            },
            {
                "label": _("Party Name"),
                "fieldname": "party_name",
                "fieldtype": "Link",
                "options": "Customer",
            },
            {
                "label": _("Update GSTIN Details"),
                "fieldname": "update_gstin_details_btn",
                "fieldtype": "Button",
                "width": 100,
            },
        ]

        return columns

    def get_data(self):
        gstin = frappe.qb.DocType("GSTIN")
        address = frappe.qb.DocType("Address")
        dynamic_link = frappe.qb.DocType("Dynamic Link")
        customer = frappe.qb.DocType("Customer")
        supplier = frappe.qb.DocType("Supplier")

        customer_query = None
        supplier_query = None
        address_query = None

        if self.filters.party_type == "Customer":
            customer_query = get_doctype_query("Customer", customer)

        if self.filters.party_type == "Supplier":
            supplier_query = get_doctype_query("Supplier", supplier)

        address_query = (
            frappe.qb.from_(address)
            .inner_join(dynamic_link)
            .on(address.name == dynamic_link.parent)
            .select(
                address.gstin,
                dynamic_link.link_doctype.as_("party_type"),
                dynamic_link.link_name.as_("party_name"),
            )
            .where(dynamic_link.link_doctype.isin(self.doctypes))
        )

        party_query = address_query

        if customer_query:
            party_query = party_query.union(customer_query)

        if supplier_query:
            party_query = party_query.union(supplier_query)

        party_query = party_query.as_("party")

        gstin_query = (
            frappe.qb.from_(party_query)
            .left_join(gstin)
            .on(gstin.gstin == party_query.gstin)
            .select(
                gstin.gstin,
                gstin.status,
                DATE_FORMAT(gstin.registration_date).as_("registration_date"),
                DATE_FORMAT(gstin.last_updated_on).as_("last_updated_on"),
                DATE_FORMAT(gstin.cancelled_date).as_("cancelled_date"),
                Case().when(gstin.is_blocked == 0, "No").else_("Yes").as_("is_blocked"),
                party_query.party_type,
                party_query.party_name,
                gstin.modified,
            )
        )

        if self.filters.status:
            gstin_query = gstin_query.where(gstin.status == self.filters.status)

        gstin_query = gstin_query.orderby(gstin.modified, order=Order.desc)

        return gstin_query.run()


def get_doctype_query(doctype_name, doctype_table):
    query = (
        frappe.qb.from_(doctype_table)
        .select(
            doctype_table.gstin,
            frappe.qb.terms.LiteralValue(f"'{doctype_name}'").as_("party_type"),
            doctype_table.name.as_("party_name"),
        )
        .where(doctype_table.gstin != "")
    )

    return query


@frappe.whitelist()
def update_gstin_status(gstin):
    updated_doc = create_or_update_gstin_status(gstin=gstin, throw=True).as_dict()
    if updated_doc.registration_date:
        updated_doc.registration_date = updated_doc.registration_date.strftime(
            "%d-%m-%Y"
        )

    if updated_doc.last_updated_on:
        updated_doc.last_updated_on = updated_doc.last_updated_on.strftime("%d-%m-%Y")

    if updated_doc.cancelled_date:
        updated_doc.cancelled_date = updated_doc.cancelled_date.strftime("%d-%m-%Y")

    updated_doc.is_blocked = "Yes" if updated_doc.is_blocked != 0 else "No"

    return updated_doc
