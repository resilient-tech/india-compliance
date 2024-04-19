// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

const DOCTYPE = "GSTR-1 Beta";
const GSTR1_Categories = {
    B2B: "B2B, SEZ, DE",
    B2CL: "B2C (Large)",
    EXP: "Exports",
    B2CS: "B2C (Others)",
    NIL_EXEMPT: "Nil-Rated, Exempted, Non-GST",
    CDNR: "Credit/Debit Notes (Registered)",
    CDNUR: "Credit/Debit Notes (Unregistered)",
    // Other Categories
    AT: "Advances Received",
    TXP: "Advances Adjusted",
    DOC_ISSUE: "Document Issued",
    HSN: "HSN Summary",
};
const GSTR1_SubCategories = {
    B2B_REGULAR: "B2B Regular",
    B2B_REVERSE_CHARGE: "B2B Reverse Charge",
    SEZWP: "SEZ with Payment of Tax",
    SEZWOP: "SEZ without Payment of Tax",
    DE: "Deemed Exports",
    EXPWP: "Export with Payment of Tax",
    EXPWOP: "Export without Payment of Tax",
    B2CL: "B2C (Large)",
    B2CS: "B2C (Others)",
    NIL_EXEMPT: "Nil-Rated, Exempted, Non-GST",
    NIL_RATED: "Nil-Rated",
    EXEMPTED: "Exempted",
    NON_GST: "Non-GST",
    CDNR: "Credit/Debit Notes (Registered)",
    CDNUR: "Credit/Debit Notes (Unregistered)",
    AT: "Advances Received",
    TXP: "Advances Adjusted",
    HSN: "HSN Summary",
    DOC_ISSUE: "Document Issued",
};

const INVOICE_TYPE = {
    [GSTR1_Categories.B2B]: [
        GSTR1_SubCategories.B2B_REGULAR,
        GSTR1_SubCategories.B2B_REVERSE_CHARGE,
        GSTR1_SubCategories.SEZWP,
        GSTR1_SubCategories.SEZWOP,
        GSTR1_SubCategories.DE,
    ],
    [GSTR1_Categories.B2CL]: [GSTR1_SubCategories.B2CL],
    [GSTR1_Categories.EXP]: [GSTR1_SubCategories.EXPWP, GSTR1_SubCategories.EXPWOP],
    [GSTR1_Categories.NIL_EXEMPT]: [GSTR1_SubCategories.NIL_EXEMPT],
    [GSTR1_Categories.CDNR]: [GSTR1_SubCategories.CDNR],
    [GSTR1_Categories.CDNUR]: [GSTR1_SubCategories.CDNUR],
    [GSTR1_Categories.AT]: [GSTR1_SubCategories.AT],
    [GSTR1_Categories.TXP]: [GSTR1_SubCategories.TXP],
    [GSTR1_Categories.HSN]: [GSTR1_SubCategories.HSN],
    [GSTR1_Categories.DOC_ISSUE]: [GSTR1_SubCategories.DOC_ISSUE],
};

const GSTR1_DataFields = {
    TRANSACTION_TYPE: "transaction_type",
    CUST_GSTIN: "customer_gstin",
    CUST_NAME: "customer_name",
    DOC_DATE: "document_date",
    DOC_NUMBER: "document_number",
    DOC_TYPE: "document_type",
    DOC_VALUE: "document_value",
    POS: "place_of_supply",
    REVERSE_CHARGE: "reverse_charge",
    TAXABLE_VALUE: "total_taxable_value",
    TAX_RATE: "tax_rate",
    IGST: "total_igst_amount",
    CGST: "total_cgst_amount",
    SGST: "total_sgst_amount",
    CESS: "total_cess_amount",

    SHIPPING_BILL_NUMBER: "shipping_bill_number",
    SHIPPING_BILL_DATE: "shipping_bill_date",
    SHIPPING_PORT_CODE: "shipping_port_code",

    EXEMPTED_AMOUNT: "exempted_amount",
    NIL_RATED_AMOUNT: "nil_rated_amount",
    NON_GST_AMOUNT: "non_gst_amount",

    HSN_CODE: "hsn_code",
    DESCRIPTION: "description",
    UOM: "uom",
    TOTAL_QUANTITY: "total_quantity",

    FROM_SR: "from_sr_no",
    TO_SR: "to_sr_no",
    TOTAL_COUNT: "total_count",
    DRAFT_COUNT: "draft_count",
    CANCELLED_COUNT: "cancelled_count",
};

const QUARTER = ["Jan-Mar", "Apr-Jun", "Jul-Sep", "Oct-Dec"];
const MONTH = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        // patch_set_active_tab(frm);
        patch_set_indicator(frm);
        frappe.require("gstr1.bundle.js").then(() => {
            frm.gstr1 = new GSTR1(frm);
            frm.trigger("company");
        });

        let filing_frequecy = await get_gstr1_filing_frequency();
        frm.filing_frequecy = filing_frequecy;

        if (filing_frequecy === "Monthly")
            frm.set_df_property("month_or_quarter", "options", MONTH);
        else frm.set_df_property("month_or_quarter", "options", QUARTER);

        set_default_fields(frm);
        // frappe.realtime.on("download_gov_gstr1_data_complete", _ => {
        //     frappe.show_alert({
        //         message: __("GSTR-1 Data Downloaded Successfully"),
        //         indicator: "green",
        //     });
        // })

        // frappe.realtime.on("compute_books_gstr1_data_complete", _ => {
        //     frappe.show_alert({
        //         message: __("GSTR-1 Data Computed Successfully"),
        //         indicator: "green",
        //     });
        // })

        frappe.realtime.on("gstr1_generation_failed", message => {
            const { error, filters } = message;
            let alert = `GSTR-1 Generation Failed for ${filters.company_gstin} - ${filters.month_or_quarter} - ${filters.year}.<br/><br/>${error}`;

            frappe.msgprint({
                title: __("GSTR-1 Generation Failed"),
                message: alert,
            });
        });

        frappe.realtime.on("gstr1_data_prepared", message => {
            const { data, filters } = message;

            if (
                frm.doc.company_gstin !== filters.company_gstin ||
                frm.doc.month_or_quarter != filters.month_or_quarter ||
                frm.doc.year != filters.year
            )
                return;

            console.log("data loaded");

            frm.doc.__onload = { data };
            frm.trigger("after_save");
            frm.refresh();
        });
    },

    async company(frm) {
        render_empty_state(frm);

        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);

        frm.set_value("company_gstin", options[0]);
    },

    company_gstin: render_empty_state,

    month_or_quarter: render_empty_state,

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
        if (data == "otp_requested") {
            india_compliance
                .authenticate_otp(frm.doc.company_gstin)
                .then(() => frm.save());
            return;
        }

        if (!data?.status) return;

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
            label: __("e-Invoice"),
            name: "e_invoice",
            _TabManager: eInvoiceTab,
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

        if (!this.data["filed"]) this.data["filed"] = this.data["books"];

        this.TABS.forEach(tab => {
            if (!this.data[tab.name]) {
                this.hide_tab(tab.name);
                tab.shown = false;
                return;
            }

            tab.shown = true;
            this.tabs[`${tab.name}_tab`].tabmanager.refresh_data(
                this.data[tab.name],
                this.status
            );
        });
    }

    refresh_view() {
        this.viewgroup.set_active_view(this.active_view);
        this.TABS.forEach(tab => {
            if (!tab.shown) return;
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
                    depends_on: tab.depends_on,
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

        // Fix css
        this.$wrapper.find(".form-tabs-list").append(`<div class="tab-actions"></div>`);

        // Remove padding around data table
        this.$wrapper.closest(".form-column").css("padding", "0px");
        this.$wrapper.closest(".row.form-section").css("padding", "0px");
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
                this,
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

        const tab_name = this.status === "Filed" ? "Filed" : "File";
        const color = this.status === "Filed" ? "green" : "orange";

        this.$wrapper.find(`[data-fieldname="filed_tab"]`).html(tab_name);
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

    download_books_as_excel() { }

    mark_as_filed() { }

    // UTILS

    hide_tab(tab_name) {
        this.$wrapper
            .find(`[data-fieldname="${tab_name}_tab"]`)
            .closest(".nav-item")
            .hide();
    }

    show_tab(tab_name) { }

    get_filter_fields() {
        const fields = [
            {
                label: "Description",
                fieldname: "description",
                fieldtype: "Autocomplete",
                options: Object.values(GSTR1_SubCategories),
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
    };

    filter_category_dialog(view_group, target_view) {
        const dialog = new frappe.ui.Dialog({
            title: __("Filter by Category"),
            fields: [
                {
                    fieldname: "description",
                    fieldtype: "Autocomplete",
                    options: Object.values(GSTR1_SubCategories),
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
    CATEGORY_COLUMNS = {};
    DEFAULT_SUMMARY = {
        // description: "",
        total_docs: 0,
        total_taxable_value: 0,
        total_igst_amount: 0,
        total_cgst_amount: 0,
        total_sgst_amount: 0,
        total_cess_amount: 0,
    };

    constructor(instance, wrapper, callback) {
        this.instance = instance;
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

        this.set_default_title();
    }

    refresh_view(view, category) {
        if (!category && view === "Details") return;

        if (view === "Details") {
            const columns_func = this.CATEGORY_COLUMNS[category];
            if (!columns_func) return;

            const columns = columns_func.call(this);
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

        this.set_title(category || this.DEFAULT_TITLE);
    }

    get_row(data, category) {
        if (category == "Nil-Rated, Exempted, Non-GST")
            self.get_data_for_nil_exempted_non_gst(data);
    }

    // SETUP

    set_title(category) {
        if (category) this.wrapper.find(".tab-title-text").text(category);
        else this.wrapper.find(".tab-title-text").html("&nbsp");
    }

    set_default_title() {
        this.set_title(this.DEFAULT_TITLE);
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
                showTotalRow: true,
                checkboxColumn: false,
                treeView: true,
                headerDropdown: [
                    {
                        label: "Collapse All Node",
                        action: () => {
                            this.datatable.datatable.rowmanager.collapseAllNodes();
                        },
                    },
                    {
                        label: "Expand All Node",
                        action: () => {
                            this.datatable.datatable.rowmanager.expandAllNodes();
                        },
                    },
                ],
                hooks: {
                    columnTotal: (firstColumn, row) => {
                        if (
                            row.colIndex === 1 &&
                            row.isTotalRow &&
                            row.content == null
                        ) {
                            row.content = "Total";
                        }
                    },
                },
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

    format_summary_table_cell(args) {
        const isDescriptionCell = args[1]?.id === "description";
        const value =
            args[2]?.indent == 0
                ? `<strong>${args[0]}</strong>`
                : isDescriptionCell
                    ? `<p style="padding-left: 15px">${args[0]}</p>`
                    : args[0];
        return `<a href="#" class="summary-description">${value}</a>`;
    }

    // DATA
    // FIXME : remove inner for-each loop
    summarize_data() {
        let sub_category_summary = this.get_sub_category_summary();

        Object.entries(INVOICE_TYPE).forEach(([category, sub_categories]) => {
            this.summary[category] = {
                ...this.DEFAULT_SUMMARY,
                description: category,
                indent: 0,
            };

            sub_categories.forEach(sub => {
                let sub_category_row = sub_category_summary[sub];

                Object.keys(this.DEFAULT_SUMMARY).forEach(key => {
                    this.summary[category][key] += sub_category_row[key];
                });

                const sub_category = `${category} - ${sub}`; // Unique description
                this.summary[sub_category] = sub_category_row;
            });
        });
    }

    // FIXME : remove `reduce`  because computed data will be in `data`
    get_sub_category_summary() {
        let sub_category_summary = {};

        Object.values(GSTR1_SubCategories).forEach(category => {
            sub_category_summary[category] = {
                ...this.DEFAULT_SUMMARY,
                description: category,
                indent: 1,
            };
        });

        Object.entries(this.data).forEach(([category, rows]) => {
            sub_category_summary[category] = rows.reduce((accumulator, row) => {
                accumulator.total_docs += 1;
                accumulator.total_taxable_value += row.taxable_value || 0;
                accumulator.total_igst_amount += row.igst_amount || 0;
                accumulator.total_cgst_amount += row.cgst_amount || 0;
                accumulator.total_sgst_amount += row.sgst_amount || 0;
                accumulator.total_cess_amount += row.cess_amount || 0;
                return accumulator;
            }, sub_category_summary[category]);
        });

        return sub_category_summary;
    }

    // COLUMNS
    get_summary_columns() {
        return [
            {
                name: "Description",
                fieldname: "description",
                width: 300,
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "Total Docs",
                fieldname: "total_docs",
                width: 100,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataFields.TAXABLE_VALUE,
                width: 180,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataFields.IGST,
                width: 150,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataFields.CGST,
                width: 150,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataFields.SGST,
                width: 150,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataFields.CESS,
                width: 150,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
        ];
    }

    get_invoice_columns() {
        return [
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataFields.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataFields.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 130,
            },
            {
                name: "Customer GSTIN",
                fieldname: GSTR1_DataFields.CUST_GSTIN,
                width: 160,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataFields.CUST_NAME,
                width: 200,
            },
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataFields.DOC_TYPE,
                width: 150,
            },
            {
                name: "Reverse Charge",
                fieldname: GSTR1_DataFields.REVERSE_CHARGE,
                align: "center",
                width: 120,
            },
            ...this.get_tax_columns(),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_export_columns() {
        return [
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataFields.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataFields.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 130,
            },
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataFields.DOC_TYPE,
                width: 150,
            },
            {
                name: "Shipping Bill Number",
                fieldname: GSTR1_DataFields.SHIPPING_BILL_NUMBER,
                width: 150,
            },
            {
                name: "Shipping Bill Date",
                fieldname: GSTR1_DataFields.SHIPPING_BILL_DATE,
                width: 120,
            },
            {
                name: "Port Code",
                fieldname: GSTR1_DataFields.SHIPPING_PORT_CODE,
                width: 100,
            },
            ...this.get_igst_tax_columns(),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_document_columns() {
        // `Transaction Type` + Invoice Columns with `Document` as title instead of `Invoice`
        return [
            {
                name: "Transaction Type",
                fieldname: GSTR1_DataFields.TRANSACTION_TYPE,
                width: 100,
            },
            {
                name: "Document Date",
                fieldname: GSTR1_DataFields.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Document Number",
                fieldname: GSTR1_DataFields.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 130,
            },
            {
                name: "Customer GSTIN",
                fieldname: GSTR1_DataFields.CUST_GSTIN,
                width: 160,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataFields.CUST_NAME,
                width: 200,
            },
            {
                name: "Document Type",
                fieldname: GSTR1_DataFields.DOC_TYPE,
                width: 150,
            },
            {
                name: "Reverse Charge",
                fieldname: GSTR1_DataFields.REVERSE_CHARGE,
                align: "center",
                width: 120,
            },
            ...this.get_tax_columns(),
            {
                name: "Document Value",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_hsn_columns() {
        return [
            {
                name: "HSN Code",
                fieldname: GSTR1_DataFields.HSN_CODE,
                width: 150,
            },
            {
                name: "Description",
                fieldname: GSTR1_DataFields.DESCRIPTION,
                width: 300,
            },
            {
                name: "UOM",
                fieldname: GSTR1_DataFields.UOM,
                width: 100,
            },
            {
                name: "Total Quantity",
                fieldname: GSTR1_DataFields.TOTAL_QUANTITY,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataFields.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataFields.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataFields.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataFields.CGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataFields.SGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataFields.CESS,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Total Value",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_documents_issued_columns() {
        return [
            {
                name: "Document Type",
                fieldname: GSTR1_DataFields.DOC_TYPE,
                width: 200,
            },
            {
                name: "Sr No From",
                fieldname: GSTR1_DataFields.FROM_SR,
                width: 150,
            },
            {
                name: "Sr No To",
                fieldname: GSTR1_DataFields.TO_SR,
                width: 150,
            },
            {
                name: "Total Count",
                fieldname: GSTR1_DataFields.TOTAL_COUNT,
                width: 120,
            },
            {
                name: "Draft Count",
                fieldname: GSTR1_DataFields.DRAFT_COUNT,
                width: 120,
            },
            {
                name: "Cancelled Count",
                fieldname: GSTR1_DataFields.CANCELLED_COUNT,
                width: 120,
            },
        ];
    }

    get_advances_received_columns() {
        return [
            ...this.get_tax_columns(),
            {
                name: "Amount Received",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_advances_adjusted_columns() {
        [
            ...this.get_tax_columns(),
            {
                name: "Amount Adjusted",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    // Common Columns

    get_tax_columns() {
        return [
            {
                name: "Place of Supply",
                fieldname: GSTR1_DataFields.POS,
                width: 150,
            },
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataFields.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataFields.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataFields.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataFields.CGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataFields.SGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataFields.CESS,
                fieldtype: "Float",
                width: 100,
            },
        ];
    }

    get_igst_tax_columns(with_pos) {
        const columns = [];

        if (with_pos)
            columns.push({
                name: "Place of Supply",
                fieldname: GSTR1_DataFields.POS,
                width: 150,
            });

        columns.push(
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataFields.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataFields.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataFields.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataFields.CESS,
                fieldtype: "Float",
                width: 100,
            }
        );

        return columns;
    }
}

class BooksTab extends TabManager {
    CATEGORY_COLUMNS = {
        // [GSTR1_Categories.NIL_EXEMPT]: this.get_document_columns,

        // SUBCATEGORIES
        [GSTR1_SubCategories.B2B_REGULAR]: this.get_invoice_columns,
        [GSTR1_SubCategories.B2B_REVERSE_CHARGE]: this.get_invoice_columns,
        [GSTR1_SubCategories.SEZWP]: this.get_invoice_columns,
        [GSTR1_SubCategories.SEZWOP]: this.get_invoice_columns,
        [GSTR1_SubCategories.DE]: this.get_invoice_columns,

        [GSTR1_SubCategories.EXPWP]: this.get_export_columns,
        [GSTR1_SubCategories.EXPWOP]: this.get_export_columns,

        [GSTR1_SubCategories.B2CL]: this.get_invoice_columns,
        [GSTR1_SubCategories.B2CS]: this.get_document_columns,

        [GSTR1_SubCategories.NIL_EXEMPT]: this.get_document_columns,

        [GSTR1_SubCategories.CDNR]: this.get_document_columns,
        [GSTR1_SubCategories.CDNUR]: this.get_document_columns,

        [GSTR1_SubCategories.AT]: this.get_advances_received_columns,
        [GSTR1_SubCategories.TXP]: this.get_advances_adjusted_columns,

        [GSTR1_SubCategories.HSN]: this.get_hsn_columns,

        [GSTR1_SubCategories.DOC_ISSUE]: this.get_documents_issued_columns,
    };

    DEFAULT_TITLE = "Summary of Books";

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

    // DATA

    get_data_for_nil_exempted_non_gst(data) {
        const out = [];
        if (data[GSTR1_SubCategories.NIL_EXEMPT]) {
            out.concat(data[GSTR1_SubCategories.NIL_EXEMPT]);
        }

        return out;
    }

    // COLUMNS

    get_advances_received_columns() {
        return [
            {
                name: "Advance Date",
                fieldname: GSTR1_DataFields.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Payment Entry Number",
                fieldname: GSTR1_DataFields.DOC_NUMBER,
                fieldtype: "Link",
                options: "Payment Entry",
                width: 130,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataFields.CUST_NAME,
                width: 200,
            },
            ...super.get_advances_received_columns(),
        ];
    }

    get_advances_adjusted_columns() {
        return [
            {
                name: "Adjustment Date",
                fieldname: GSTR1_DataFields.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Adjustment Entry Number",
                fieldname: GSTR1_DataFields.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 130,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataFields.CUST_NAME,
                width: 200,
            },
            ...this.get_tax_columns(),
            {
                name: "Amount Adjusted",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }
}

class FiledTab extends TabManager {
    CATEGORY_COLUMNS = {
        [GSTR1_SubCategories.B2B_REGULAR]: this.get_invoice_columns,
        [GSTR1_SubCategories.B2B_REVERSE_CHARGE]: this.get_invoice_columns,
        [GSTR1_SubCategories.SEZWP]: this.get_invoice_columns,
        [GSTR1_SubCategories.SEZWOP]: this.get_invoice_columns,
        [GSTR1_SubCategories.DE]: this.get_invoice_columns,

        [GSTR1_SubCategories.EXPWP]: this.get_export_columns,
        [GSTR1_SubCategories.EXPWOP]: this.get_export_columns,

        [GSTR1_SubCategories.B2CL]: this.get_b2cl_columns,
        [GSTR1_SubCategories.B2CS]: this.get_b2cs_columns,

        [GSTR1_SubCategories.NIL_EXEMPT]: this.get_nil_exempt_columns,

        [GSTR1_SubCategories.CDNR]: this.get_document_columns,
        [GSTR1_SubCategories.CDNUR]: this.get_cdnur_columns,

        [GSTR1_SubCategories.AT]: this.get_advances_received_columns,
        [GSTR1_SubCategories.TXP]: this.get_advances_adjusted_columns,

        [GSTR1_SubCategories.HSN]: this.get_hsn_columns,
        [GSTR1_SubCategories.DOC_ISSUE]: this.get_documents_issued_columns,
    };

    DEFAULT_TITLE = "";

    setup_actions() {
        this.add_tab_custom_button("Download Excel", () =>
            this.download_filed_as_excel()
        );

        if (this.status === "Filed") return;

        this.add_tab_custom_button("Download JSON", () => console.log("hi"));
        this.add_tab_custom_button("Mark as Filed", () => console.log("hi"));
    }

    // ACTIONS

    download_filed_as_excel() { }

    // COLUMNS

    get_b2cl_columns() {
        return [
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataFields.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataFields.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 130,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataFields.CUST_NAME,
                width: 200,
            },
            ...this.get_igst_tax_columns(true),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_b2cs_columns() {
        return [
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataFields.DOC_TYPE,
                width: 100,
            },
            ...this.get_tax_columns(),
        ];
    }

    get_nil_exempt_columns() {
        return [
            {
                name: "Description",
                fieldname: GSTR1_DataFields.DOC_TYPE,
                width: 200,
            },
            {
                name: "Nil-Rated Supplies",
                fieldname: GSTR1_DataFields.NIL_RATED_AMOUNT,
                fieldtype: "Currency",
                width: 150,
            },
            {
                name: "Exempted Supplies",
                fieldname: GSTR1_DataFields.EXEMPTED_AMOUNT,
                fieldtype: "Currency",
                width: 150,
            },
            {
                name: "Non-GST Supplies",
                fieldname: GSTR1_DataFields.NON_GST_AMOUNT,
                fieldtype: "Currency",
                width: 150,
            },
            {
                name: "Total Taxable Value",
                fieldname: GSTR1_DataFields.TAXABLE_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_cdnur_columns() {
        return [
            {
                name: "Transaction Type",
                fieldname: GSTR1_DataFields.TRANSACTION_TYPE,
                width: 100,
            },
            {
                name: "Document Date",
                fieldname: GSTR1_DataFields.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Document Number",
                fieldname: GSTR1_DataFields.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 130,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataFields.CUST_NAME,
                width: 200,
            },
            {
                name: "Document Type",
                fieldname: GSTR1_DataFields.DOC_TYPE,
                width: 150,
            },
            ...this.get_igst_tax_columns(true),
            {
                name: "Document Value",
                fieldname: GSTR1_DataFields.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }
}

class eInvoiceTab extends FiledTab {
    setup_actions() { }

    set_default_title() {
        this.DEFAULT_TITLE = "e-Invoices as in GSTR-1";
        super.set_default_title();
    }
}

class ReconcileTab extends FiledTab {
    set_default_title() {
        if (this.instance.data.status === "Filed")
            this.DEFAULT_TITLE = "Difference between Books vs Filed";
        else this.DEFAULT_TITLE = "Difference between Books vs e-Invoices";

        super.set_default_title();
    }

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
    set_previous_month_or_quarter(frm);
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

function set_previous_month_or_quarter(frm) {
    const currentDate = new Date();
    if (frm.filing_frequecy === "Monthly") {
        let prevMonthIdx = currentDate.getMonth() - 1;
        prevMonthIdx = prevMonthIdx < 0 ? 11 : prevMonthIdx;

        frm.set_value("month_or_quarter", MONTH[prevMonthIdx]);
    } else {
        const currentMonth = currentDate.getMonth();
        let prevQuarterIdx;
        if (currentMonth <= 2) {
            prevQuarterIdx = 3;
        } else if (currentMonth <= 5) {
            prevQuarterIdx = 0;
        } else if (currentMonth <= 8) {
            prevQuarterIdx = 1;
        } else {
            prevQuarterIdx = 2;
        }
        frm.set_value("month_or_quarter", QUARTER[prevQuarterIdx]);
    }
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

async function get_gstr1_filing_frequency() {
    return new Promise((resolve, reject) => {
        frappe.call({
            method: "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta.get_gstr1_filing_frequency",
            callback: function (r) {
                resolve(r.message);
            },
        });
    });
}
