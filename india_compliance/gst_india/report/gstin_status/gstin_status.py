# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import IfNull, IsNull, LiteralValue


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
        self.is_naming_series = "Naming Series" in (
            frappe.db.get_single_value("Buying Settings", "supp_master_name"),
            frappe.db.get_single_value("Selling Settings", "cust_master_name"),
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
                "label": _("Party"),
                "fieldname": "party",
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

        if self.is_naming_series:
            columns.insert(
                2,
                {
                    "label": _("Party Name"),
                    "fieldname": "party_name",
                    "fieldtype": "Data",
                    "width": 220,
                },
            )

        return columns

    def get_data(self):
        gstin = frappe.qb.DocType("GSTIN")

        party_query = self._get_party_query()

        gstin_query_select_fields = [
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
            party_query.party,
        ]

        if self.is_naming_series:
            gstin_query_select_fields.append(party_query.party_name)

        gstin_query = (
            frappe.qb.from_(party_query)
            .left_join(gstin)
            .on(gstin.gstin == party_query.gstin)
            .select(*gstin_query_select_fields)
            .orderby(gstin.modified, order=Order.desc)
        )

        if self.filters.status:
            gstin_query = gstin_query.where(gstin.status == self.filters.status)

        return gstin_query.run(as_dict=True)

    def _get_party_query(self):
        address = frappe.qb.DocType("Address")
        dynamic_link = frappe.qb.DocType("Dynamic Link")

        party_query_select_fields = [
            address.gstin,
            dynamic_link.link_doctype.as_("party_type"),
            dynamic_link.link_name.as_("party"),
        ]

        party_query = (
            frappe.qb.from_(address)
            .inner_join(dynamic_link)
            .on(address.name == dynamic_link.parent)
        )

        if self.is_naming_series:
            customer = frappe.qb.DocType("Customer")
            supplier = frappe.qb.DocType("Supplier")
            party_query = (
                party_query.inner_join(customer)
                .on(dynamic_link.link_name == customer.name)
                .inner_join(supplier)
                .on(dynamic_link.link_name == supplier.name)
            )

            party_query_select_fields.append(
                Case()
                .when(dynamic_link.link_doctype == "Customer", customer.customer_name)
                .when(dynamic_link.link_doctype == "Supplier", supplier.supplier_name)
                .as_("party_name")
            )

        party_query = (
            party_query.select(*party_query_select_fields)
            .where(dynamic_link.link_doctype.isin(self.doctypes))
            .where(IfNull(address.gstin, "") != "")
            .distinct()
        ).as_("party")

        for doctype in self.doctypes:
            party_query = party_query.union(self._get_party_doctype_query(doctype))

        return party_query

    def _get_party_doctype_query(self, doctype):
        dt = frappe.qb.DocType(doctype)

        select_fields = [
            dt.gstin,
            LiteralValue(f"'{doctype}'").as_("party_type"),
            dt.name.as_("party"),
        ]

        if self.is_naming_series:
            select_fields.append(dt[f"{doctype.lower()}_name"].as_("party_name"))

        query = (
            frappe.qb.from_(dt).select(*select_fields).where(IfNull(dt.gstin, "") != "")
        )

        return query
