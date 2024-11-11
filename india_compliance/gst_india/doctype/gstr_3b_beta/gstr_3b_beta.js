// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

const api_enabled = india_compliance.is_api_enabled();

frappe.ui.form.on("GSTR-3B Beta", {
    async setup(frm) {
        await frappe.require("gstr3b.bundle.js");
        frm.gstr3b = new GSTR3B(frm);

        set_options_for_year(frm);
        set_options_for_month(frm);
    },

    async company(frm) {
        render_empty_state(frm);
        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);

        if (!frm.doc.company_gstin) frm.set_value("company_gstin", options[0]);
    },

    company_gstin(frm) {
        render_empty_state(frm);
    },

    year(frm) {
        render_empty_state(frm);
        set_options_for_month(frm);
    },

    month(frm) {
        render_empty_state(frm);
    },

    refresh(frm) {
        // Primary Action
        frm.disable_save();
        frm.page.set_primary_action(__("Get Invoices"), async () => {
            const { message } = await frm.call("get_invoice_data");
            frm.doc.__invoice_data = message;
            frm.refresh();
            frm.gstr3b.render_data_tables();
        });

        frm.add_custom_button(
            __("Accept"),
            () => {
                bulk_update_status(frm, "Accept");
            },
            __("Actions")
        );
        frm.add_custom_button(
            __("Reject"),
            () => {
                bulk_update_status(frm, "Reject");
            },
            __("Actions")
        );
        frm.add_custom_button(
            __("Pending"),
            () => {
                bulk_update_status(frm, "Pending");
            },
            __("Actions")
        );
        frm.add_custom_button(
            __("No Action"),
            () => {
                bulk_update_status(frm, "No Action");
            },
            __("Actions")
        );
    },
});

class GSTR3B {
    constructor(frm) {
        this.init(frm);
        this.render_tab_group();
        this.setup_filter_button();
        this.render_data_tables();
    }

    init(frm) {
        this.frm = frm;
        this.$wrapper = this.frm.get_field("invoice_html").$wrapper;
        this._tabs = ["invoice", "summary"];
    }

    refresh() {
        this._tabs.forEach(tab => {
            this.tabs[`${tab}_tab`].refresh(this[`get_${tab}_data`]());
        });
    }

    render_tab_group() {
        this.tab_group = new frappe.ui.FieldGroup({
            fields: [
                {
                    //hack: for the FieldGroup(Layout) to avoid rendering default "details" tab
                    fieldtype: "Section Break",
                },
                {
                    label: "Match Summary",
                    fieldtype: "Tab Break",
                    fieldname: "summary_tab",
                    active: 1,
                },
                {
                    fieldtype: "HTML",
                    fieldname: "summary_data",
                },
                {
                    label: "Document View",
                    fieldtype: "Tab Break",
                    fieldname: "invoice_tab",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "invoice_data",
                },
            ],
            body: this.$wrapper,
            frm: this.frm,
        });

        this.tab_group.make();

        // make tabs_dict for easy access
        this.tabs = Object.fromEntries(
            this.tab_group.tabs.map(tab => [tab.df.fieldname, tab])
        );
    }

    setup_filter_button() {
        this.filter_group = new india_compliance.FilterGroup({
            doctype: "GSTR-3B Beta",
            parent: this.$wrapper.find(".form-tabs-list"),
            on_change: () => {
                this.refresh();
            },
        });
    }

    render_data_tables() {
        this._tabs.forEach(tab => {
            this.tabs[`${tab}_tab`] = new india_compliance.DataTableManager({
                $wrapper: this.tab_group.get_field(`${tab}_data`).$wrapper,
                columns: this[`get_${tab}_columns`](),
                data: this[`get_${tab}_data`](),
                options: {
                    cellHeight: 55,
                },
            });
        });
    }

    get_summary_columns() {
        return [
            {
                label: "Match Status",
                fieldname: "match_status",
                width: 200,
                _value: (...args) => `<a href="#" class='match-status'>${args[0]}</a>`,
            },
            {
                label: "Count <br>2A/2B Docs",
                fieldname: "inward_supply_count",
                width: 120,
                align: "center",
            },
            {
                label: "Count <br>Purchase Docs",
                fieldname: "purchase_count",
                width: 120,
                align: "center",
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_difference",
                width: 180,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_difference",
                width: 180,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "% Action Taken",
                fieldname: "action_taken",
                width: 120,
                align: "center",
                _value: (...args) => {
                    return (
                        roundNumber(
                            (args[2].action_taken_count / args[2].total_docs) * 100,
                            2
                        ) + " %"
                    );
                },
            },
        ];
    }

    get_summary_data() {
        if (!this.frm.doc.__invoice_data) return [];

        const data = {};
        this.frm.doc.__invoice_data.forEach(row => {
            let new_row = data[row.match_status];
            if (!new_row) {
                new_row = data[row.match_status] = {
                    match_status: row.match_status,
                    inward_supply_count: 0,
                    purchase_count: 0,
                    action_taken_count: 0,
                    total_docs: 0,
                    tax_difference: 0,
                    taxable_value_difference: 0,
                };
            }
            if (row.inward_supply_name) new_row.inward_supply_count += 1;
            if (row.purchase_invoice_name) new_row.purchase_count += 1;
            if (row.action != "No Action") new_row.action_taken_count += 1;
            new_row.total_docs += 1;
            new_row.tax_difference += row.tax_difference || 0;
            new_row.taxable_value_difference += row.taxable_value_difference || 0;
        });

        return Object.values(data);
    }

    get_invoice_data() {
        if (!this.frm.doc.__invoice_data) return [];

        const data = [];
        this.frm.doc.__invoice_data.forEach(row => {
            data.push({
                supplier_name_gstin: this.get_supplier_name_gstin(row),
                invoice_no: row.bill_no,
                invoice_type: row._inward_supply.supply_type,
                invoice_status: row._inward_supply.invoice_status,
                match_status: row.match_status,
                linked_doc: row.purchase_invoice_name,
                tax_difference: row.tax_difference,
                taxable_value_difference: row.taxable_value_difference,
            });
        });

        return data;
    }

    get_invoice_columns() {
        return [
            {
                label: "Supplier Name",
                fieldname: "supplier_name_gstin",
                align: "center",
                width: 200,
            },
            {
                label: "Invoice No.",
                fieldname: "invoice_no",
                align: "center",
                width: 150,
            },
            {
                label: "Invoice Type",
                fieldname: "invoice_type",
                align: "center",
                width: 80,
            },
            {
                label: "Status",
                fieldname: "invoice_status",
                align: "center",
                width: 100,
                fieldtype: "html",
            },
            {
                label: "Match Status",
                fieldname: "match_status",
                align: "center",
                width: 100,
            },
            {
                label: "Linked Voucher",
                fieldname: "linked_doc",
                align: "center",
                width: 150,
                fieldtype: "Dynamic Link",
                options: "linked_voucher_type",
            },
            {
                label: "Tax Difference",
                fieldname: "tax_difference",
                align: "center",
                width: 150,
            },
            {
                label: "Taxable Value Difference",
                fieldname: "taxable_value_difference",
                align: "center",
                width: 150,
            },
        ];
    }

    get_supplier_name_gstin(row) {
        return `
        ${row.supplier_name}
        <br />
        <a href="#" style="font-size: 0.9em;" class="supplier-gstin">
            ${row.supplier_gstin || ""}
        </a>
        `;
    }
}

function set_options_for_year(frm) {
    const today = new Date();
    const current_year = today.getFullYear();
    const start_year = 2017;
    const year_range = current_year - start_year + 1;
    let options = Array.from({ length: year_range }, (_, index) => start_year + index);
    options = options.reverse().map(year => year.toString());

    set_field_options("year", options);
    frm.set_value("year", current_year.toString());
}

function set_options_for_month(frm) {
    /**
     * Set options for Month based on the year and current date
     * 1. If the year is current year, then options are till current month
     * 2. If the year is 2017, then options are from July to December
     * 3. Else, options are all months
     *
     * @param {Object} frm
     */

    const today = new Date();
    const current_year = String(today.getFullYear());
    const current_month_idx = today.getMonth();
    let options;

    if (!frm.doc.year) frm.doc.year = current_year;

    if (frm.doc.year === current_year) {
        // Options for current year till current month
        options = india_compliance.MONTH.slice(0, current_month_idx + 1);
    } else if (frm.doc.year === "2017") {
        // Options for 2017 from July to December
        options = india_compliance.MONTH.slice(6);
    } else {
        options = india_compliance.MONTH;
    }

    set_field_options("month", options);

    let month_to_set;

    // set second last option as default
    if (frm.doc.year === current_year) month_to_set = options[options.length - 2];
    // set last option as default
    else month_to_set = options[options.length - 1];

    if (month_to_set !== frm.doc.month) frm.set_value("month", month_to_set);
}

function get_first_last_day(year, month) {
    // Convert the string to a Date object
    const givenDate = moment(`${year}-${month}-01`);

    // Get the first day of the month
    const from_date = givenDate.startOf("month").format("YYYY-MM-DD");

    // Get the last day of the month
    const to_date = givenDate.endOf("month").format("YYYY-MM-DD");

    return { from_date, to_date };
}

function render_empty_state(frm) {
    frm.doc.__invoice_data = null;
    frm.refresh();
}
