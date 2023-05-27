// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["e-Invoice Summary"] = {
    filters: [
        {
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            fieldname: "company",
            label: __("Company"),
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldtype: "Link",
            options: "Customer",
            fieldname: "customer",
            label: __("Customer"),
        },
        {
            fieldtype: "Date",
            reqd: 1,
            fieldname: "from_date",
            label: __("From Date"),
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            fieldtype: "Date",
            reqd: 1,
            fieldname: "to_date",
            label: __("To Date"),
            default: frappe.datetime.get_today(),
        },
        {
            fieldtype: "Select",
            fieldname: "status",
            label: __("e-Invoice Status"),
            options: "\nPending\nGenerated\nCancelled\nFailed",
        },
        {
            fieldtype: "Select",
            fieldname: "exceptions",
            label: __("e-Invoice Exceptions"),
            options: "\ne-Invoice Not Generated\nInvoice Cancelled but not e-Invoice",
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname == "einvoice_status" && value) {
            if (value == "Pending")
                value = `<span class="bold" style="color: var(--text-on-orange)">${value}</span>`;
            else if (value == "Generated")
                value = `<span class="bold" style="color: var(--text-on-green)">${value}</span>`;
            else if (value == "Cancelled")
                value = `<span class="bold" style="color: var(--text-on-red)">${value}</span>`;
            else if (value == "Failed")
                value = `<span class="bold"  style="color: var(--text-on-red)">${value}</span>`;
        }

        return value;
    },
};
