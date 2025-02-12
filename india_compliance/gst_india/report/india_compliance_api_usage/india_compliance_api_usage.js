// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["India Compliance API Usage"] = {
    filters: [
        {
            "fieldname": "from_date",
            "label": __("From"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.add_months(frappe.datetime.now_date(), -6)
        },
        {
            "fieldname": "to_date",
            "label": __("To"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.now_date()
        },
        {
            "fieldname": "report_by",
            "label": __("Report by"),
            "fieldtype": "Select",
            "options": [
                "Endpoint",
                "Linked Document",
                "Date"
            ],
            "default": "Endpoint"
        },
    ],

    onload(query_report) {
        query_report.filters.forEach(filter => {
            if (filter.fieldtype === "Date") {
                filter.datepicker.update(
                    { maxDate: new Date() }
                )
            }
        });
    }
};
