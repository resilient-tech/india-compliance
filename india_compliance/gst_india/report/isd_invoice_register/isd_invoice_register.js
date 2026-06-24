// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

// Amount columns that should be summed in the total row. Returns (Purchase Invoice view)
// and credit notes (ISD Invoice view) are already stored negative, so a plain sum nets them out.
const AMOUNT_FIELDS = [
    // Purchase Invoice view
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "cess_amount",
    "cess_non_advol_amount",
    // ISD Invoice view
    "distributed_igst",
    "distributed_cgst",
    "distributed_sgst",
    "distributed_cess",
    "distributed_cess_non_advol",
];

frappe.query_reports["ISD Invoice Register"] = {
    filters: [
        {
            fieldname: "report_view",
            label: __("Report View"),
            fieldtype: "Select",
            options: "Purchase Invoice\nISD Invoice",
            default: "Purchase Invoice",
            reqd: 1,
            on_change: function () {
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: function () {
                frappe.query_report.set_filter_value({
                    company_gstin: "",
                    distributor_gstin: "",
                    recipient_gstin: "",
                    purchase_invoice: "",
                });
            },
            get_query: function () {
                return { filters: { country: "India" } };
            },
        },
        {
            fieldname: "date_range",
            label: __("Date Range"),
            fieldtype: "DateRange",
            default: [india_compliance.last_month_start(), india_compliance.last_month_end()],
            reqd: 1,
            width: "80",
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "Purchase Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company, "Company", false, true);
            },
        },
        {
            fieldname: "distributor_gstin",
            label: __("Distributor GSTIN"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company, "Company", false, true);
            },
        },
        {
            fieldname: "recipient_gstin",
            label: __("Recipient GSTIN"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company, "Company", true);
            },
        },
        {
            fieldname: "purchase_invoice",
            label: __("Purchase Invoice"),
            fieldtype: "Link",
            options: "Purchase Invoice",
            depends_on: 'eval:doc.report_view === "Purchase Invoice"',
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return { filters: { company, is_isd_applicable: 1, docstatus: 1 } };
            },
        },
        {
            fieldname: "is_return",
            label: __("Is Return"),
            fieldtype: "Check",
            depends_on: 'eval:doc.report_view === "Purchase Invoice"',
        },
        {
            fieldname: "is_credit_note",
            label: __("Is Credit Note"),
            fieldtype: "Check",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
        },
        {
            fieldname: "recipient_state",
            label: __("Recipient State"),
            fieldtype: "Autocomplete",
            depends_on: 'eval:doc.report_view === "ISD Invoice"',
            options: frappe.boot.india_state_options,
        },
    ],

    async onload(report) {
        // Pre-select the first ISD GSTIN; company_gstin & distributor_gstin share the same source.
        const company = report.get_filter_value("company");
        if (!company) return;

        const { query, params } = india_compliance.get_gstin_query(company, "Company", false, true);
        const { message } = await frappe.call({ method: query, args: params });
        if (!message?.length) return;

        report.set_filter_value({ company_gstin: message[0], distributor_gstin: message[0] });
    },

    // Override datatable hook for column total calculation
    get_datatable_options(datatable_options) {
        datatable_options.hooks = {
            columnTotal: custom_report_column_total,
        };

        return datatable_options;
    },
};

function custom_report_column_total(...args) {
    const column = args[1].column;
    const column_field = column.fieldname;
    if (![...AMOUNT_FIELDS, "total_invoice_value", "taxable_value"].includes(column_field)) return "";

    const { data } = this.datamanager;
    const indices = this.datamanager.getFilteredRowIndices();

    // base_grand_total repeats across the per-rate rows of an invoice; count it once per invoice.
    if (column_field === "total_invoice_value" || column_field == "taxable_value") {
        const seen = new Set();
        return indices.reduce((total, index) => {
            const row = data[index];
            if (seen.has(row.invoice_name)) return total;
            seen.add(row.invoice_name);
            return total + flt(row[column_field]);
        }, 0);
    }

    if (!AMOUNT_FIELDS.includes(column_field)) return "";

    return indices.reduce((total, index) => total + flt(data[index][column_field]), 0);
}
