// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

const DOCTYPE = "GSTR-1 Beta";
const GSTR_1_SUB_CATEGORIES = {
    B2B_REGULAR: "B2B Regular",
    B2B_REVERSE_CHARGE: "B2B Reverse Charge",
    SEZWP: "SEZ with Payment of Tax",
    SEZWOP: "SEZ without Payment of Tax",
    DE: "Deemed Exports",
    EXPWP: "Export with Payment of Tax",
    EXPWOP: "Export without Payment of Tax",
    B2CL: "B2C (Large)",
    B2CS: "B2C (Others)",
    NIL_RATED: "Nil Rated",
    EXEMPTED: "Exempted",
    NON_GST: "Non-GST",
    CDNR: "Credit/Debit Notes (Registered)",
    CDNUR: "Credit/Debit Notes (Unregistered)",
    AT: "Advances Received",
    TXP: "Advances Adjusted",
    HSN: "HSN Summary",
    DOC_ISSUE: "Document Issued",
};

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        // patch_set_active_tab(frm);
        patch_set_indicator(frm);
        frappe.require("gstr1.bundle.js").then(() => {
            frm.gstr1 = new GSTR1(frm);
            frm.trigger("company");
        });
        set_default_fields(frm);
    },

    async company(frm) {
        render_empty_state(frm);

        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);

        frm.set_value("company_gstin", options[0]);
    },

    company_gstin: render_empty_state,

    month: render_empty_state,

    year: render_empty_state,

    refresh(frm) {
        // Primary Action
        frm.disable_save();
        frm.page.set_primary_action(__("Generate"), () => frm.save());

        // Indicators
        frm.gstr1?.render_indicator();
    },

    before_save(frm) {
        frm.doc.__unsaved = true;
    },

    after_save(frm) {
        const data = frm.doc.__onload?.data;
        frm.gstr1.status = data.status;
        frm.gstr1.refresh_data(data);
    },
});

class GSTR1 {
    // Render page / Setup Listeners / Setup Data
    TABS = [
        {
            label: __("Books"),
            name: "books",
            is_active: true,
            _TabManager: BooksTab,
        },
        {
            label: __("Reconcile"),
            name: "reconcile",
            _TabManager: ReconcileTab,
        },
        {
            label: __("Filed"),
            name: "filed",
            _TabManager: FiledTab,
        },
    ];

    constructor(frm) {
        this.init(frm);
        this.render();
    }

    init(frm) {
        this.frm = frm;
        this.data = frm.doc._data;
        this.filters = [];
        this.$wrapper = frm.fields_dict.tabs_html.$wrapper;
    }

    refresh_data(data) {
        if (data) this.data = data;

        this.TABS.forEach(tab => {
            this.tabs[`${tab.name}_tab`].tabmanager.refresh_data(
                this.data[tab.name],
                this.status
            );
        });
    }

    refresh_view() {
        this.viewgroup.set_active_view(this.active_view);
        this.TABS.forEach(tab => {
            this.tabs[`${tab.name}_tab`].tabmanager.refresh_view(
                this.active_view,
                this.filter_category
            );
        });
    }

    refresh_filter() {
        const category_filter = this.filters.filter(row => row[1] === "description");
        this.filter_category = category_filter.length ? category_filter[0][3] : null;

        if (this.filter_category) this.active_view = "Details";
        else this.active_view = "Summary";

        this.refresh_view();
    }

    // RENDER

    render() {
        this.render_tab_group();
        this.render_indicator();
        this.setup_filter_button();
        this.render_view_groups();
        this.render_tabs();
    }

    render_tab_group() {
        const tab_fields = this.TABS.reduce(
            (acc, tab) => [
                ...acc,
                {
                    fieldtype: "Tab Break",
                    fieldname: `${tab.name}_tab`,
                    label: __(tab.label),
                    active: tab.is_active ? 1 : 0,
                },
                {
                    fieldtype: "HTML",
                    fieldname: `${tab.name}_html`,
                },
            ],
            []
        );

        this.tab_group = new frappe.ui.FieldGroup({
            fields: [
                {
                    //hack: for the FieldGroup(Layout) to avoid rendering default "details" tab
                    fieldtype: "Section Break",
                },
                ...tab_fields,
            ],
            body: this.$wrapper,
            frm: this.frm,
        });
        this.tab_group.make();

        // make tabs_dict for easy access
        this.tabs = Object.fromEntries(
            this.tab_group.tabs.map(tab => [tab.df.fieldname, tab])
        );

        this.$wrapper.find(".form-tabs-list").append(`<div class="tab-actions"></div>`);
    }

    render_view_groups() {
        this.active_view = "Summary";
        const wrapper = this.$wrapper.find(".tab-actions").find(".custom-button-group");

        this.viewgroup = new india_compliance.ViewGroup({
            $wrapper: wrapper,
            view_names: ["Summary", "Details"],
            active_view: this.active_view,
            parent: this,
            callback: this.change_view,
        });
    }

    render_tabs() {
        this.TABS.forEach(tab => {
            const wrapper = this.tab_group.get_field(`${tab.name}_html`).$wrapper;
            this.tabs[`${tab.name}_tab`].tabmanager = new tab._TabManager(
                wrapper,
                this.apply_filters
            );
        });
    }

    render_indicator() {
        if (!this.status) {
            this.frm.page.clear_indicator();
            return;
        }

        let color = this.status === "Filed" ? "green" : "orange";
        this.frm.page.set_indicator(this.status, color);
    }

    // SETUP

    setup_filter_button() {
        this.filter_group = new india_compliance.FilterGroup({
            doctype: DOCTYPE,
            parent: this.$wrapper.find(".tab-actions"),
            filter_options: {
                fieldname: "description",
                filter_fields: this.get_filter_fields(),
            },
            on_change: () => {
                this.filters = this.filter_group.get_filters();
                this.refresh_filter();
            },
        });
    }

    // ACTIONS

    download_books_as_excel() {}

    mark_as_filed() {}

    // UTILS

    get_filter_fields() {
        const fields = [
            {
                label: "Description",
                fieldname: "description",
                fieldtype: "Autocomplete",
                options: Object.values(GSTR_1_SUB_CATEGORIES),
            },
        ];

        fields.forEach(field => (field.parent = DOCTYPE));
        return fields;
    }

    refresh_filter_fields() {
        this.filter_group.filter_options.filter_fields = this.get_filter_fields();
    }

    get_autocomplete_options(field) {
        const options = [];
        this.data.forEach(row => {
            if (row[field] && !options.includes(row[field])) options.push(row[field]);
        });
        return options;
    }

    apply_filters = async category => {
        await this.filter_group.push_new_filter([
            DOCTYPE,
            "description",
            "=",
            category,
        ]);
        this.filter_group.apply();
    };

    change_view = (view_group, target_view) => {
        const current_view = this.active_view;

        if (!this.filter_category && current_view === "Summary")
            return this.filter_category_dialog(view_group, target_view);

        view_group.set_active_view(target_view);
        this.active_view = target_view;

        this.refresh_view();

        console.log(this.active_view);
    };

    filter_category_dialog(view_group, target_view) {
        const dialog = new frappe.ui.Dialog({
            title: __("Filter by Category"),
            fields: [
                {
                    fieldname: "description",
                    fieldtype: "Autocomplete",
                    options: Object.values(GSTR_1_SUB_CATEGORIES),
                    label: __("Category"),
                },
            ],
            primary_action: async () => {
                const { description } = dialog.get_values();
                if (!description) return;

                dialog.hide();
                await this.apply_filters(description);
                this.change_view(view_group, target_view);
            },
        });

        dialog.show();
    }
}

class TabManager {
    CATEGORY_COLUMNS = {}
    DEFAULT_SUMMARY = {
        description: "",
        total_docs: 0,
        total_taxable_amount: 0,
        total_igst_amount: 0,
        total_cgst_amount: 0,
        total_sgst_amount: 0,
        total_cess_amount: 0,
    };

    constructor(wrapper, callback) {
        this.wrapper = wrapper;
        this.callback = callback;
        this.reset_data();
        this.setup_wrapper();
        this.setup_datatable(wrapper);
    }

    reset_data() {
        this.data = {}; // Raw Data
        this.filtered_data = {}; // Filtered Data / Details View
        this.summary = {};
    }

    refresh_data(data, status) {
        this.data = data;
        this.status = status;
        this.setup_actions();
        this.summarize_data();
        this.datatable.refresh(Object.values(this.summary));
    }

    refresh_view(view, category) {
        if (!category && view === "Details") return;

        if (view === "Details") {
            const columns_func = this.CATEGORY_COLUMNS[category];
            console.log(columns_func);
            const columns = columns_func ? columns_func() : this.get_b2b_columns();
            this.setup_datatable(this.wrapper, this.data[category], columns);

        } else if (view === "Summary") {
            let filtered_summary = Object.values(this.summary);
            if (category)
                filtered_summary = filtered_summary.filter(
                    row => row.description === category
                );

            this.setup_datatable(
                this.wrapper,
                filtered_summary,
                this.get_summary_columns()
            );
        }

        this.set_title(category);
    }

    // SETUP

    set_title(category) {
        if (category) this.wrapper.find(".tab-title-text").text(category);
        else this.wrapper.find(".tab-title-text").html("&nbsp");
    }

    setup_wrapper() {
        this.wrapper.append(`
            <div class="tab-title m-3 d-flex justify-content-between align-items-center">
                <div class="tab-title-text">&nbsp</div>
                <div class="custom-button-group page-actions custom-actions hidden-xs hidden-md"></div>
            </div>
            <div class="data-table"></div>
        `);
    }

    setup_datatable(wrapper, data, columns) {
        const _columns = columns || this.get_summary_columns();
        const _data = data || [];

        this.datatable = new india_compliance.DataTableManager({
            $wrapper: wrapper.find(".data-table"),
            columns: _columns,
            data: _data,
            options: {
                cellHeight: 55,
            },
            no_data_message: __("No data found"),
        });

        this.setup_datatable_listeners();
    }

    setup_datatable_listeners() {
        const me = this;
        this.datatable.$datatable.on(
            "click",
            ".summary-description",
            async function (e) {
                e.preventDefault();

                const summary_description = $(this).text();
                me.callback && me.callback(summary_description);
            }
        );
    }

    setup_actions() { }

    // UTILS

    add_tab_custom_button(label, action) {
        let button = this.wrapper.find(
            `button[data-label="${encodeURIComponent(label)}"]`
        );
        if (button.length) return;

        $(`
            <button
            class="btn btn-default ellipsis"
            data-label="${encodeURIComponent(label)}">
                ${label}
            </button>
        `)
            .appendTo(this.wrapper.find(".custom-button-group"))
            .on("click", action);
    }

    // DATA
    summarize_data() {
        Object.values(GSTR_1_SUB_CATEGORIES).forEach(category => {
            this.summary[category] = { ...this.DEFAULT_SUMMARY, description: category };
        });

        Object.entries(this.data).forEach(([category, rows]) => {
            this.summary[category] = rows.reduce((accumulator, row) => {
                accumulator.total_docs += 1;
                accumulator.total_taxable_amount += row.total_taxable_amount || 0;
                accumulator.total_igst_amount += row.total_igst_amount || 0;
                accumulator.total_cgst_amount += row.total_cgst_amount || 0;
                accumulator.total_sgst_amount += row.total_sgst_amount || 0;
                accumulator.total_cess_amount += row.total_cess_amount || 0;
                return accumulator;
            }, this.summary[category]);
        });
    }

    // COLUMNS
    get_summary_columns() {
        return [
            {
                name: "Description",
                fieldname: "description",
                width: 300,
                _value: (...args) =>
                    `<a href = "#" class="summary-description">${args[0]}</a>`,
            },
            {
                name: "Total Docs",
                fieldname: "total_docs",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "Taxable Amomunt",
                fieldname: "total_taxable_amount",
                width: 180,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "IGST",
                fieldname: "total_igst_amount",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "CGST",
                fieldname: "total_cgst_amount",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "SGST",
                fieldname: "total_sgst_amount",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "CESS",
                fieldname: "total_cess_amount",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
        ];
    }

    get_b2b_columns() { }
}

class BooksTab extends TabManager {
    CATEGORY_COLUMNS = {
        "B2B Regular": this.get_invoice_columns,
        "B2B Reverse Charge": this.get_invoice_columns,
        "SEZ with Payment of Tax": this.get_invoice_columns,
        "HSN Summary": this.get_hsn_columns,
    };

    setup_actions() {
        this.add_tab_custom_button("Download Excel", () =>
            this.download_books_as_excel()
        );
    }

    // ACTIONS

    download_books_as_excel() {
        frappe.call({
            method: "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta.download_books_as_excel",
            args: { data: this.data },
            callback: r => {
                frappe.msgprint(r.message);
            },
        });
    }

    // COLUMNS

    get_invoice_columns() {
        return [
            {
                name: "Invoice Number",
                fieldname: "invoice_number",
                width: 150,
            },
            {
                name: "Customer GSTIN",
                fieldname: "customer_gstin",
                width: 150,
            },
            {
                name: "Invoice Value",
                fieldname: "invoice_value",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "Taxable Value",
                fieldname: "taxable_value",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "IGST",
                fieldname: "igst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "CGST",
                fieldname: "cgst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "SGST",
                fieldname: "sgst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
        ];
    }

    get_hsn_columns() {
        return [
            {
                name: "HSN Code",
                fieldname: "hsn_code",
                width: 150,
            },
            {
                name: "Description",
                fieldname: "description",
                width: 300,
            },
            {
                name: "UQC",
                fieldname: "uqc",
                width: 100,
            },
            {
                name: "Total Quantity",
                fieldname: "total_quantity",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "Total Value",
                fieldname: "total_value",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "Total Taxable Value",
                fieldname: "total_taxable_value",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "Total Integrated Tax",
                fieldname: "total_igst",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "Total Central Tax",
                fieldname: "total_cgst",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "Total State/UT Tax",
                fieldname: "total_sgst",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
        ];
    }
}

class ReconcileTab extends TabManager {
    setup_actions() {
        this.add_tab_custom_button("Download Excel", () =>
            this.download_reconcile_as_excel()
        );
    }

    download_reconcile_as_excel() {
        frappe.call({
            method: "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta.download_reconcile_as_excel",
            args: { data: this.data },
            callback: r => {
                frappe.msgprint(r.message);
            },
        });
    }
}

class FiledTab extends TabManager {
    setup_actions() {
        this.add_tab_custom_button("Download Excel", () =>
            this.download_filed_as_excel()
        );

        console.log(this.status);
        if (this.status === "Filed") return;

        this.add_tab_custom_button("Download JSON", () => console.log("hi"));
        this.add_tab_custom_button("Mark as Filed", () => console.log("hi"));
    }
}

// UTILITY FUNCTIONS

function patch_set_active_tab(frm) {
    const set_active_tab = frm.set_active_tab;
    frm.set_active_tab = function (...args) {
        set_active_tab.apply(this, args);
        frm.refresh();
    };
}

function patch_set_indicator(frm) {
    frm.toolbar.set_indicator = function () { };
}

function set_default_fields(frm) {
    set_default_company_gstin(frm);
    set_default_year(frm);
    set_previous_month(frm);
}

async function set_default_company_gstin(frm) {
    frm.set_value("company_gstin", "");

    const company = frm.doc.company;
    const { message: gstin_list } = await frappe.call(
        "india_compliance.gst_india.utils.get_gstin_list",
        { party: company }
    );

    if (gstin_list && gstin_list.length) {
        frm.set_value("company_gstin", gstin_list[0]);
    }
}

function set_default_year(frm) {
    const year = new Date().getFullYear().toString();
    frm.set_value("year", year);
}

function set_previous_month(frm) {
    var previous_month_date = new Date();
    previous_month_date.setMonth(previous_month_date.getMonth() - 1);
    const month = previous_month_date.toLocaleDateString("en", { month: "long" });
    frm.set_value("month", month);
}

function get_year_list(current_date) {
    const current_year = current_date.getFullYear();
    const start_year = 2017;
    const year_range = current_year - start_year + 1;
    const options = Array.from(
        { length: year_range },
        (_, index) => start_year + index
    );
    return options.reverse().map(year => year.toString());
}

function render_empty_state(frm) {
    frm.doc.__onload = null;
    frm.refresh();
}
