# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case, Order


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
                "width": 100,
            },
        ]

        return columns

    def get_data(self):
        GSTIN = frappe.qb.DocType("GSTIN")
        Address = frappe.qb.DocType("Address")
        DynamicLink = frappe.qb.DocType("Dynamic Link")
        Customer = frappe.qb.DocType("Customer")
        Supplier = frappe.qb.DocType("Supplier")

        customer_query = None
        supplier_query = None
        address_query = None

        if self.filters.reference_party in ["All", "Customer"]:
            customer_query = (
                frappe.qb.from_(Customer)
                .select(
                    Customer.gstin,
                    frappe.qb.terms.LiteralValue("'Customer'").as_("reference_party"),
                    Customer.name.as_("party_name"),
                )
                .where(Customer.gstin != "")
            )

        if self.filters.reference_party in ["All", "Supplier"]:
            supplier_query = (
                frappe.qb.from_(Supplier)
                .select(
                    Supplier.gstin,
                    frappe.qb.terms.LiteralValue("'Supplier'").as_("reference_party"),
                    Supplier.name.as_("party_name"),
                )
                .where(Supplier.gstin != "")
            )

        address_query = (
            frappe.qb.from_(Address)
            .inner_join(DynamicLink)
            .on(Address.name == DynamicLink.parent)
            .select(
                Address.gstin,
                DynamicLink.link_doctype.as_("reference_party"),
                DynamicLink.link_name.as_("party_name"),
            )
            .where(DynamicLink.link_doctype.isin(self.doctypes))
        )

        if customer_query:
            party_query = customer_query
        else:
            party_query = supplier_query

        if customer_query and supplier_query:
            party_query = party_query.union(supplier_query)

        party_query = party_query.union(address_query)
        party_query = party_query.as_("party")

        # Main query to join GSTIN with the combined party_query

        gstin_query = (
            frappe.qb.from_(party_query)
            .left_join(GSTIN)
            .on(GSTIN.gstin == party_query.gstin)
            .select(
                GSTIN.gstin,
                GSTIN.status,
                GSTIN.registration_date,
                GSTIN.last_updated_on,
                GSTIN.cancelled_date,
                Case().when(GSTIN.is_blocked == 0, "No").else_("Yes").as_("is_blocked"),
                party_query.reference_party,
                party_query.party_name,
                GSTIN.modified,
            )
        )

        if self.filters.status != "All":
            gstin_query = gstin_query.where(GSTIN.status == self.filters.status)

        gstin_query = gstin_query.orderby(GSTIN.modified, order=Order.desc)

        return gstin_query.run()
