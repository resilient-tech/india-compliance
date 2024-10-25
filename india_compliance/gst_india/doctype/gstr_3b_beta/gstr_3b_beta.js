// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

const api_enabled = india_compliance.is_api_enabled();

frappe.ui.form.on("GSTR-3B Beta", {
    async setup(frm) {
        await frappe.require("purchase_reconciliation_tool.bundle.js");

        frm.gstr3b = new GSTR3B(frm);

        frm.trigger("company");

        set_options_for_year(frm);
        set_options_for_month(frm);
        frm.gstr3b.filter_invoices();
    },

    async company(frm) {
        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);

        if (!frm.doc.company_gstin) frm.set_value("company_gstin", options[0]);
    },
    company_gstin(frm) {
        frm.gstr3b.filter_invoices();
    },

    year(frm) {
        set_options_for_month(frm);
        frm.gstr3b.filter_invoices();
    },
    month(frm) {
        frm.gstr3b.filter_invoices();
    },

    refresh(frm) {
        // Primary Action
        frm.disable_save();
        frm.page.set_primary_action(__("Save Actions"), async () => {
            frm.gstr3b.update_invoice_data();
            await frm.save();
            frm.gstr3b.generate_gstr3b();
        });

        // add custom buttons
        if (api_enabled) {
            frm.add_custom_button(__("Download Invoices"), () => {
                // Do something
            });
        }

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
        this.frm = frm;
        this.generate_gstr3b();
        this.frm.filtered_invoices = this.frm.doc.invoice_data;
    }

    generate_gstr3b() {
        this.fetch_invoice_data();
        setTimeout(() => {
            this.render_data_table();
        }, 100);
    }

    async fetch_invoice_data() {
        if (!this.frm.doc.is_modified) {
            await this.frm.call("fetch_invoice_data").then(r => {
                this.frm.set_value("invoice_data", r.message);
            });
            this.filter_invoices();
        }
    }

    update_invoice_data() {
        for (const key in this.frm.filtered_invoices) {
            const invoice = this.frm.filtered_invoices[key];
            if (invoice["is_dirty"]) {
                this.frm.doc.invoice_data[key] = invoice;
            }
        }
        this.frm.filtered_invoices = {};
    }

    filter_invoices() {
        this.frm.filtered_invoices = {};
        const { from_date, to_date } = get_first_last_day(
            this.frm.doc.year,
            this.frm.doc.month
        );

        for (const key in this.frm.doc.invoice_data) {
            const invoice = this.frm.doc.invoice_data[key];
            if (
                invoice["company"] === this.frm.doc.company &&
                invoice["company_gstin"] === this.frm.doc.company_gstin &&
                invoice["invoice_date"] >= from_date &&
                invoice["invoice_date"] <= to_date
            ) {
                this.frm.filtered_invoices[key] = this.frm.doc.invoice_data[key];
            }
        }
        this.render_data_table();
    }

    get_data() {
        let data = [];
        for (const key in this.frm.filtered_invoices) {
            data.push(this.frm.filtered_invoices[key]);
        }

        return data;
    }

    get_columns() {
        return [
            {
                label: "GSTIN of Supplier",
                fieldname: "supplier_gstin",
                align: "center",
                width: 180,
            },
            {
                label: "Supplier",
                fieldname: "supplier",
                align: "center",
                width: 120,
            },
            {
                label: "Invoice No.",
                fieldname: "invoice_no",
                align: "center",
                width: 80,
            },
            {
                label: "Invoice Type",
                fieldname: "invoice_type",
                align: "center",
                width: 80,
            },
            {
                label: "Accept",
                fieldname: "accept",
                align: "center",
                width: 80,
                fieldtype: "html",
                _value: (...args) => get_icon(...args, "#4bf90b"),
            },
            {
                label: "Reject",
                fieldname: "reject",
                align: "center",
                width: 80,
                fieldtype: "html",
                _value: (...args) => get_icon(...args, "#f21a02"),
            },
            {
                label: "Pending",
                fieldname: "pending",
                align: "center",
                width: 80,
                fieldtype: "html",
                _value: (...args) => get_icon(...args, "#FFD43B"),
            },
            {
                label: "Status",
                fieldname: "invoice_status",
                align: "center",
                width: 100,
                fieldtype: "html",
            },
        ];
    }

    render_data_table() {
        this.data_table = new india_compliance.DataTableManager({
            $wrapper: this.frm.get_field("invoices_html").$wrapper,
            columns: this.get_columns(),
            data: this.get_data(),
            options: {
                cellHeight: 55,
            },
        });
        this.set_listners();
    }

    set_listners() {
        const me = this;

        this.data_table.$datatable.on("click", ".btn.accept", function (e) {
            me.change_status(me, $(this).attr("data-name"), "Accept");
        });

        this.data_table.$datatable.on("click", ".btn.reject", function (e) {
            me.change_status(me, $(this).attr("data-name"), "Reject");
        });

        this.data_table.$datatable.on("click", ".btn.pending", function (e) {
            me.change_status(me, $(this).attr("data-name"), "Pending");
        });
    }

    change_status(me, invoice_name, status) {
        const curr_status = me.frm.filtered_invoices[invoice_name]["invoice_status"];

        if (!me.frm.is_modified) me.frm.is_modified = 1;
        me.frm.filtered_invoices[invoice_name]["invoice_status"] =
            status === curr_status ? "No Action" : status;
        me.frm.filtered_invoices[invoice_name]["is_dirty"] = 1;

        me.render_data_table();
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
    // set second last option as default
    if (frm.doc.year === current_year) {
        frm.set_value("month", options[options.length - 2]);
    }
    // set last option as default
    else frm.set_value("month", options[options.length - 1]);
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

function get_icon(value, column, data, color) {
    style = "-o";
    switch (data["invoice_status"]) {
        case "Accept":
            if (column.fieldname === "accept") style = "";
            break;
        case "Reject":
            if (column.fieldname === "reject") style = "";
            break;
        case "Pending":
            if (column.fieldname === "pending") style = "";
            break;
    }

    const hash = data["invoice_name"];
    return `<button class="btn ${column.fieldname}" data-name="${hash}">
                <i class="fa fa-circle${style}" style="color: ${color}"></i>
            </button>`;
}

function bulk_update_status(frm, status) {
    const checked_rows_indexes =
        frm.gstr3b.data_table.datatable.rowmanager.getCheckedRows();

    if (!checked_rows_indexes.length) {
        frappe.msgprint("Please select invoices");
        return;
    }

    const modified_invoice_names = checked_rows_indexes.map(
        i => frm.gstr3b.data_table.data[i]["invoice_name"]
    );
    update_status(frm, modified_invoice_names, status);
}

function update_status(frm, invoice_names, status) {
    for (const invoice_name of invoice_names) {
        frm.filtered_invoices[invoice_name]["invoice_status"] = status;
        frm.filtered_invoices[invoice_name]["is_dirty"] = 1;
    }
    frm.gstr3b.render_data_table();
}
