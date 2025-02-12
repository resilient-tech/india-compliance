# Copyright (c) 2025, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Date, Replace

from india_compliance.gst_india.api_classes.base import BASE_URL


def execute(filters: dict | None = None):
    report = IndiaComplianceAPIUsageReport(filters=filters)
    columns = report.get_columns()
    data = report.get_data()

    return columns, data


class IndiaComplianceAPIUsageReport:
    def __init__(self, filters: dict | None = None):
        self.from_data = filters.from_date
        self.to_date = filters.to_date
        self.report_by = filters.report_by

    def get_columns(self) -> list[dict]:
        if self.report_by == "Endpoint":
            return self._get_columns_by_endpoint()

        if self.report_by == "Date":
            return self._get_columns_by_date()

        return self._get_columns_by_linked_doctype()

    def _get_columns_by_endpoint(self):
        columns = [
            {
                "label": _("Endpoint"),
                "fieldname": "endpoint",
                "fieldtype": "Data",
                "width": 400,
            },
            {
                "label": _("API Requests Count"),
                "fieldname": "api_requests_count",
                "fieldtype": "Int",
                "width": 200,
            },
        ]

        return columns

    def _get_columns_by_date(self):
        columns = [
            {
                "label": _("Date"),
                "fieldname": "date",
                "fieldtype": "Date",
                "width": 250,
            },
            {
                "label": _("API Requests Count"),
                "fieldname": "api_requests_count",
                "fieldtype": "Int",
                "width": 200,
            },
        ]

        return columns

    def _get_columns_by_linked_doctype(self):
        columns = [
            {
                "label": _("Reference DocType"),
                "fieldname": "reference_doctype",
                "fieldtype": "Link",
                "options": "DocType",
                "width": 200,
            },
            {
                "label": _("Reference Document"),
                "fieldname": "reference_docname",
                "fieldtype": "Dynamic Link",
                "options": "reference_doctype",
                "width": 200,
            },
            {
                "label": _("API Requests Count"),
                "fieldname": "api_requests_count",
                "fieldtype": "Int",
                "width": 200,
            },
        ]

        return columns

    def get_data(self) -> list[dict]:
        if self.report_by == "Endpoint":
            return self._get_data_by_endpoint()

        if self.report_by == "Date":
            return self._get_data_by_date()

        return self._get_data_by_linked_doctype()

    def _get_data_by_endpoint(self):
        integration_requests = frappe.qb.DocType("Integration Request")

        query = (
            frappe.qb.from_(integration_requests)
            .select(
                # Replace base url for all API endpoints
                Replace(integration_requests.url, BASE_URL, "").as_("endpoint"),
                Count("*").as_("api_requests_count"),
            )
            .where(integration_requests.creation >= self.from_data)
            .where(integration_requests.creation <= self.to_date)
            .groupby(integration_requests.url)
        )

        return query.run(as_dict=True)

    def _get_data_by_date(self):
        integration_requests = frappe.qb.DocType("Integration Request")

        query = (
            frappe.qb.from_(integration_requests)
            .select(
                Date(integration_requests.creation).as_("date"),
                Count("*").as_("api_requests_count"),
            )
            .where(integration_requests.creation >= self.from_data)
            .where(integration_requests.creation <= self.to_date)
            .groupby("date")
        )

        return query.run(as_dict=True)

    def _get_data_by_linked_doctype(self):
        integration_requests = frappe.qb.DocType("Integration Request")

        query = (
            frappe.qb.from_(integration_requests)
            .select(
                integration_requests.reference_doctype.as_("reference_doctype"),
                integration_requests.reference_docname.as_("reference_docname"),
                Count("*").as_("api_requests_count"),
            )
            .where(integration_requests.creation >= self.from_data)
            .where(integration_requests.creation <= self.to_date)
            .groupby(
                integration_requests.reference_doctype,
                integration_requests.reference_docname,
            )
        )

        return query.run(as_dict=True)
