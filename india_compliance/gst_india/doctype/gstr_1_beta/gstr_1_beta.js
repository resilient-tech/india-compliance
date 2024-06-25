// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

const DOCTYPE = "GSTR-1 Beta";
const GSTR1_Category = {
    B2B: "B2B, SEZ, DE",
    EXP: "Exports",
    B2CL: "B2C (Large)",
    B2CS: "B2C (Others)",
    NIL_EXEMPT: "Nil-Rated, Exempted, Non-GST",
    CDNR: "Credit/Debit Notes (Registered)",
    CDNUR: "Credit/Debit Notes (Unregistered)",
    // Other Categories
    AT: "Advances Received",
    TXP: "Advances Adjusted",
    HSN: "HSN Summary",
    DOC_ISSUE: "Document Issued",
};

const GSTR1_SubCategory = {
    B2B_REGULAR: "B2B Regular",
    B2B_REVERSE_CHARGE: "B2B Reverse Charge",
    SEZWP: "SEZ With Payment of Tax",
    SEZWOP: "SEZ Without Payment of Tax",
    DE: "Deemed Exports",
    EXPWP: "Export With Payment of Tax",
    EXPWOP: "Export Without Payment of Tax",
    B2CL: "B2C (Large)",
    B2CS: "B2C (Others)",
    NIL_EXEMPT: "Nil-Rated, Exempted, Non-GST",
    CDNR: "Credit/Debit Notes (Registered)",
    CDNUR: "Credit/Debit Notes (Unregistered)",

    AT: "Advances Received",
    TXP: "Advances Adjusted",
    HSN: "HSN Summary",
    DOC_ISSUE: "Document Issued",

    SUPECOM_52: "TCS collected by E-commerce Operator u/s 52",
    SUPECOM_9_5: "GST Payable on RCM by E-commerce Operator u/s 9(5)",
};

const INVOICE_TYPE = {
    [GSTR1_Category.B2B]: [
        GSTR1_SubCategory.B2B_REGULAR,
        GSTR1_SubCategory.B2B_REVERSE_CHARGE,
        GSTR1_SubCategory.SEZWP,
        GSTR1_SubCategory.SEZWOP,
        GSTR1_SubCategory.DE,
    ],
    [GSTR1_Category.B2CL]: [GSTR1_SubCategory.B2CL],
    [GSTR1_Category.EXP]: [GSTR1_SubCategory.EXPWP, GSTR1_SubCategory.EXPWOP],
    [GSTR1_Category.NIL_EXEMPT]: [GSTR1_SubCategory.NIL_EXEMPT],
    [GSTR1_Category.CDNR]: [GSTR1_SubCategory.CDNR],
    [GSTR1_Category.CDNUR]: [GSTR1_SubCategory.CDNUR],
    [GSTR1_Category.AT]: [GSTR1_SubCategory.AT],
    [GSTR1_Category.TXP]: [GSTR1_SubCategory.TXP],
    [GSTR1_Category.HSN]: [GSTR1_SubCategory.HSN],
    [GSTR1_Category.DOC_ISSUE]: [GSTR1_SubCategory.DOC_ISSUE],
};

const GSTR1_DataField = {
    TRANSACTION_TYPE: "transaction_type",
    CUST_GSTIN: "customer_gstin",
    ECOMMERCE_GSTIN: "ecommerce_gstin",
    CUST_NAME: "customer_name",
    DOC_DATE: "document_date",
    DOC_NUMBER: "document_number",
    DOC_TYPE: "document_type",
    DOC_VALUE: "document_value",
    POS: "place_of_supply",
    DIFF_PERCENTAGE: "diff_percentage",
    REVERSE_CHARGE: "reverse_charge",
    TAXABLE_VALUE: "total_taxable_value",
    TAX_RATE: "tax_rate",
    IGST: "total_igst_amount",
    CGST: "total_cgst_amount",
    SGST: "total_sgst_amount",
    CESS: "total_cess_amount",
    UPLOAD_STATUS: "upload_status",

    SHIPPING_BILL_NUMBER: "shipping_bill_number",
    SHIPPING_BILL_DATE: "shipping_bill_date",
    SHIPPING_PORT_CODE: "shipping_port_code",

    EXEMPTED_AMOUNT: "exempted_amount",
    NIL_RATED_AMOUNT: "nil_rated_amount",
    NON_GST_AMOUNT: "non_gst_amount",

    HSN_CODE: "hsn_code",
    DESCRIPTION: "description",
    UOM: "uom",
    QUANTITY: "quantity",

    FROM_SR: "from_sr_no",
    TO_SR: "to_sr_no",
    TOTAL_COUNT: "total_count",
    DRAFT_COUNT: "draft_count",
    CANCELLED_COUNT: "cancelled_count",
};

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        patch_set_indicator(frm);
        frappe.require("gstr1.bundle.js").then(() => {
            frm.gstr1 = new GSTR1(frm);
            frm.trigger("company");
        });

        frm.filing_frequency = gst_settings.filing_frequency;

        // Set Default Values
        set_default_company_gstin(frm);
        set_options_for_year(frm);
        set_options_for_month_or_quarter(frm);

        frm.__setup_complete = true;

        // Setup Listeners
        frappe.realtime.on("is_not_latest_data", message => {
            const { filters } = message;

            const [month_or_quarter, year] =
                india_compliance.get_month_year_from_period(filters.period);

            if (
                frm.doc.company_gstin !== filters.company_gstin ||
                frm.doc.month_or_quarter != month_or_quarter ||
                frm.doc.year != year
            )
                return;

            if (frm.$wrapper.find(".form-message.orange").length) return;
            frm.set_intro(
                __(
                    "Books data was updated after the computation of GSTR-1 data. Please generate GSTR-1 again."
                ),
                "orange"
            );
        });

        frappe.realtime.on("show_message", message => {
            frappe.msgprint(message);
        });

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

            frappe.after_ajax(() => {
                frm.doc.__onload = { data };
                frm.trigger("after_save");
            });
        });
    },

    async company(frm) {
        render_empty_state(frm);

        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);

        frm.set_value("company_gstin", options[0]);
    },

    company_gstin: render_empty_state,

    month_or_quarter(frm) {
        render_empty_state(frm);
    },

    year(frm) {
        render_empty_state(frm);
        set_options_for_month_or_quarter(frm);
    },

    refresh(frm) {
        // Primary Action
        frm.disable_save();
        frm.page.set_primary_action(__("Generate"), () => frm.save());
    },

    before_save(frm) {
        frm.doc.__unsaved = true;
    },

    async after_save(frm) {
        const data = frm.doc.__onload?.data;
        if (!frm._otp_requested && data == "otp_requested") {
            frm._otp_requested = true;

            india_compliance
                .authenticate_otp(frm.doc.company_gstin)
                .then(() => frm.save());
            return;
        }

        frm._otp_requested = false;

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
            label: __("Unfiled"),
            name: "unfiled",
            _TabManager: UnfiledTab,
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
        this.render_indicator();

        // clear filters if any and set default view
        this.active_view = "Summary";
        this.filter_group.filter_x_button.click();

        if (data) this.data = data;

        // set data for filing return
        if (!this.data["filed"]) {
            // deepcopy
            const filed = JSON.parse(JSON.stringify(this.data["books"]));
            Object.assign(filed, filed.aggregate_data);

            this.data["filed"] = filed;
            this.data["filed_summary"] = this.data["books_summary"];
        }

        // set idx for reconcile rows (for detail view)
        if (this.data["reconcile"]) {
            Object.values(this.data["reconcile"]).forEach(category => {
                category instanceof Array &&
                    category.forEach((row, idx) => {
                        row.idx = idx;
                    });
            });
        }

        this.set_output_gst_balances();

        // refresh tabs
        this.TABS.forEach(_tab => {
            const tab_name = _tab.name;
            const tab = this.tabs[`${tab_name}_tab`];

            if (!this.data[tab_name]) {
                tab.hide();
                _tab.shown = false;
                return;
            }

            tab.show();
            _tab.shown = true;
            tab.tabmanager.refresh_data(
                this.data[tab_name],
                this.data[`${tab_name}_summary`],
                this.status
            );
        });
    }

    async refresh_view() {
        // for change in view (Summary/Detailed)
        this.viewgroup.set_active_view(this.active_view);

        this.toggle_filter_selector();

        let detailed_view_filters = [];
        if (this.active_view === "Detailed") {
            detailed_view_filters = this.filter_group.get_filters();
        }

        // refresh tabs
        this.TABS.forEach(tab => {
            if (!tab.shown) return;
            this.tabs[`${tab.name}_tab`].tabmanager.refresh_view(
                this.active_view,
                this.filter_category,
                detailed_view_filters
            );
        });
    }

    // RENDER

    render() {
        this.render_tab_group();
        this.render_indicator();
        this.setup_filter_button();
        this.render_view_groups();
        this.render_tabs();
        this.setup_detail_view_listener();
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
                    //hack: for the FieldGroup(Layout) to avoid rendering default "Detailed" tab
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
            view_names: ["Summary", "Detailed"],
            active_view: this.active_view,
            parent: this,
            callback: this.change_view,
        });

        this.viewgroup.disable_view(
            "Detailed",
            "Click on a category from summary to view details"
        );
    }

    render_tabs() {
        this.TABS.forEach(tab => {
            const wrapper = this.tab_group.get_field(`${tab.name}_html`).$wrapper;
            this.tabs[`${tab.name}_tab`].tabmanager = new tab._TabManager(
                this,
                wrapper,
                this.show_filtered_category,
                this.filter_detailed_view
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
        this.frm.refresh();
    }

    // SETUP

    setup_filter_button() {
        this.filter_group = new india_compliance.FilterGroup({
            doctype: DOCTYPE,
            parent: this.$wrapper.find(".tab-actions"),
            filter_options: {
                fieldname: "description",
                filter_fields: this.get_category_filter_fields(),
            },
            on_change: () => {
                if (this.is_category_changed) {
                    this.is_category_changed = false;
                    return;
                }

                this.refresh_view();
            },
        });

        this.toggle_filter_selector();
    }

    setup_detail_view_listener() {
        const me = this;
        this.$wrapper.on("click", ".btn.eye.reconcile-row", function (e) {
            const row_index = $(this).attr("data-row-index");
            const data = me.data.reconcile[me.filter_category][row_index];

            const category_columns = me.tabs.filed_tab.tabmanager.category_columns;
            const field_label_map = category_columns.map(col => [
                col.fieldname,
                col.name,
            ]);

            new DetailViewDialog(data, field_label_map);
        });
    }

    // UTILS

    show_filtered_category = category => {
        category = category.trim();

        if (category != this.filter_category) {
            this.is_category_changed = true;
        }

        this.filter_category = category;

        if (this.filter_category) this.active_view = "Detailed";
        else this.active_view = "Summary";

        this.viewgroup.enable_view("Detailed");

        this.refresh_filter_options();
        this.refresh_view();
    };

    refresh_filter_options() {
        const filter_options = this.filter_group.filter_options;
        this.filter_fields = this.get_category_filter_fields();

        if (!this.filter_fields.length) return;

        filter_options.fieldname = this.filter_fields[0].fieldname;
        filter_options.filter_fields = this.filter_fields;

        if (this.is_category_changed) {
            this.filter_group.filter_x_button.click();
        }
    }

    get_category_filter_fields() {
        let fields = [];

        if (
            [
                GSTR1_SubCategory.B2B_REGULAR,
                GSTR1_SubCategory.B2B_REVERSE_CHARGE,
                GSTR1_SubCategory.SEZWOP,
                GSTR1_SubCategory.SEZWP,
                GSTR1_SubCategory.DE,
                GSTR1_SubCategory.CDNR,
            ].includes(this.filter_category)
        ) {
            fields = [
                {
                    label: "Customer GSTIN",
                    fieldname: GSTR1_DataField.CUST_GSTIN,
                    fieldtype: "Data",
                },
                {
                    label: "Reverse Charge",
                    fieldname: GSTR1_DataField.REVERSE_CHARGE,
                    fieldtype: "Data",
                },
                {
                    label: "Place of Supply",
                    fieldname: GSTR1_DataField.POS,
                    fieldtype: "Data",
                },
            ];
        } else if (
            [GSTR1_SubCategory.EXPWP, GSTR1_SubCategory.EXPWOP].includes(
                this.filter_category
            )
        ) {
            fields = [
                {
                    label: "Port Code",
                    fieldname: GSTR1_DataField.SHIPPING_PORT_CODE,
                    fieldtype: "Data",
                },
            ];
        } else if (
            [
                GSTR1_SubCategory.B2CL,
                GSTR1_SubCategory.B2CS,
                GSTR1_SubCategory.AT,
                GSTR1_SubCategory.TXP,
                GSTR1_SubCategory.CDNUR,
            ].includes(this.filter_category)
        ) {
            fields = [
                {
                    label: "Place of Supply",
                    fieldname: GSTR1_DataField.POS,
                    fieldtype: "Data",
                },
            ];
        } else if (
            [GSTR1_SubCategory.NIL_EXEMPT, GSTR1_SubCategory.DOC_ISSUE].includes(
                this.filter_category
            )
        ) {
            fields = [
                {
                    label: "Document Type",
                    fieldname: GSTR1_DataField.DOC_TYPE,
                    fieldtype: "Data",
                },
            ];
        } else if (this.filter_category === GSTR1_SubCategory.HSN) {
            fields = [
                {
                    label: "HSN Code",
                    fieldname: GSTR1_DataField.HSN_CODE,
                    fieldtype: "Data",
                },
                {
                    label: "UOM",
                    fieldname: GSTR1_DataField.UOM,
                    fieldtype: "Data",
                },
            ];
        }

        fields.forEach(field => (field.parent = DOCTYPE));
        return fields;
    }

    filter_detailed_view = async (fieldname, value) => {
        await this.filter_group.push_new_filter([DOCTYPE, fieldname, "=", value]);
        this.filter_group.apply();
    };

    show_summary_view = () => {
        this.viewgroup.set_active_view("Summary");
        this.change_view("Summary");
    };

    change_view = target_view => {
        const current_view = this.active_view;

        if (!this.filter_category && current_view === "Summary") return;

        this.active_view = target_view;
        this.refresh_view();
    };

    toggle_filter_selector() {
        if (this.active_view === "Detailed" && this.filter_fields.length)
            this.$wrapper.find(".filter-selector").show();
        else this.$wrapper.find(".filter-selector").hide();
    }

    async set_output_gst_balances() {
        //Checks if gst-ledger-difference element is there and removes if already present
        const gst_liability = await get_net_gst_liability(this.frm);

        if ($(".gst-ledger-difference").length) {
            $(".gst-ledger-difference").remove();
        }

        $(function () {
            $('[data-toggle="tooltip"]').tooltip();
        });

        const net_transactions = {
            IGST: gst_liability["total_igst_amount"] || 0,
            CGST: gst_liability["total_cgst_amount"] || 0,
            SGST: gst_liability["total_sgst_amount"] || 0,
            CESS: gst_liability["total_cess_amount"] || 0,
        };

        const ledger_balance_cards = Object.entries(net_transactions)
            .map(
                ([type, net_amount]) => `
            <div>
                <h5>${type} Account</h5>
                <h4 class="text-center">
                    ${format_currency(net_amount)}</h4>
            </div>`
            )
            .join("");

        const gst_liability_html = `
        <div
            class="gst-ledger-difference w-100"
            style="border-bottom: 1px solid var(--border-color);"
        >
            <div class="m-2 text-center" style="font-size: 13px">
                <span>Net Output GST Liability (Credit - Debit)</span>
            </div>
            <div class="m-3 d-flex justify-content-around align-items-center">
                ${ledger_balance_cards}
            </div>
        </div>`;

        let element = $('[data-fieldname="data_section"]');
        element.prepend(gst_liability_html);
    }
}

class TabManager {
    DEFAULT_NO_DATA_MESSAGE = __("No Data");
    CATEGORY_COLUMNS = {};
    DEFAULT_SUMMARY = {
        // description: "",
        no_of_records: 0,
        total_taxable_value: 0,
        total_igst_amount: 0,
        total_cgst_amount: 0,
        total_sgst_amount: 0,
        total_cess_amount: 0,
    };

    constructor(instance, wrapper, summary_view_callback, detailed_view_callback) {
        this.DEFAULT_TITLE = "";
        this.DEFAULT_SUBTITLE = "";
        this.creation_time_string = "";

        this.instance = instance;
        this.wrapper = wrapper;
        this.summary_view_callback = summary_view_callback;
        this.detailed_view_callback = detailed_view_callback;

        this.reset_data();
        this.setup_wrapper();
        this.setup_datatable(wrapper);
        this.setup_footer(wrapper);
    }

    reset_data() {
        this.data = {}; // Raw Data
        this.filtered_data = {}; // Filtered Data / Detailed View
        this.summary = {};
    }

    refresh_data(data, summary_data, status) {
        this.data = data;
        this.summary = summary_data;
        this.status = status;
        this.remove_tab_custom_buttons();
        this.setup_actions();
        this.datatable.refresh(this.summary);
        this.set_default_title();
        this.set_creation_time_string();
    }

    refresh_view(view, category, filters) {
        if (!category && view === "Detailed") return;

        this.filter_category = category;
        let subtitle = "";

        if (view === "Detailed") {
            this.filter_fieldnames = this.instance.filter_fields.map(
                filter => filter.fieldname
            );

            const columns_func = this.CATEGORY_COLUMNS[category];
            if (!columns_func) return;

            this.category_columns = columns_func.call(this);
            this.setup_datatable(
                this.wrapper,
                this.filter_data(this.data[category], filters),
                this.category_columns
            );
            this.set_title(category, null, true);
        } else if (view === "Summary") {
            this.setup_datatable(
                this.wrapper,
                this.summary,
                this.get_summary_columns()
            );
            subtitle = this.DEFAULT_SUBTITLE;
            this.set_title(this.DEFAULT_TITLE, subtitle);
        }

        this.setup_footer(this.wrapper);
        this.set_creation_time_string();
    }

    filter_data(data, filters) {
        if (!data) return [];
        if (!filters || !filters.length) return data;

        return data.filter(row => {
            return filters.every(filter =>
                india_compliance.FILTER_OPERATORS[filter[2]](
                    filter[3] || "",
                    row[filter[1]] || ""
                )
            );
        });
    }

    // SETUP

    set_title(title, subtitle, with_back_button = false) {
        if (title) this.wrapper.find(".tab-title-text").text(title);
        else this.wrapper.find(".tab-title-text").html("&nbsp");

        if (subtitle) this.wrapper.find(".tab-subtitle-text").text(subtitle);
        else this.wrapper.find(".tab-subtitle-text").html("");

        if (with_back_button) this.wrapper.find(".tab-back-button").show();
        else this.wrapper.find(".tab-back-button").hide();
    }

    set_default_title() {
        this.set_title(this.DEFAULT_TITLE, this.DEFAULT_SUBTITLE);
    }

    setup_wrapper() {
        this.wrapper.append(`
            <div class="m-3 d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    <div class="tab-back-button mr-4">
                        <a><i class="fa fa-arrow-left"></i></a>
                    </div>
                    <div>
                        <div class="tab-title-text">&nbsp</div>
                        <div class="tab-subtitle-text"></div>
                    </div>
                </div>
                <div class="custom-button-group page-actions custom-actions hidden-xs hidden-md"></div>
            </div>
            <div class="data-table"></div>
            <div class="report-footer" style="padding: var(--padding-sm)">
                <button class="btn btn-xs btn-default expand" data-action="expand_all_rows">
                    ${__("Expand All")}</button>
                <button class="btn btn-xs btn-default collapse" data-action="collapse_all_rows">
                    ${__("Collapse All")}</button>
            </div>
        `);

        this.setup_back_button_listener();
    }

    setup_back_button_listener() {
        this.wrapper.find(".tab-back-button").on("click", () => {
            this.instance.show_summary_view();
        });
    }

    setup_datatable(wrapper, data, columns) {
        const _columns = columns || this.get_summary_columns();
        const _data = data || [];
        const treeView = this.instance.active_view === "Summary";

        this.datatable = new india_compliance.DataTableManager({
            $wrapper: wrapper.find(".data-table"),
            columns: _columns,
            data: _data,
            options: {
                showTotalRow: true,
                checkboxColumn: false,
                treeView: treeView,
                noDataMessage: this.DEFAULT_NO_DATA_MESSAGE,
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
                    columnTotal: (_, row) => {
                        if (this.instance.active_view !== "Summary") return null;

                        if (row.colIndex === 1)
                            return (row.content = "Total Liability");

                        const column_field = row.column.fieldname;
                        if (!this.summary) return null;

                        const total = this.summary.reduce((acc, row) => {
                            if (row.indent !== 1) return acc;
                            if (
                                row.consider_in_total_taxable_value &&
                                ["no_of_records", "total_taxable_value"].includes(
                                    column_field
                                )
                            )
                                acc += row[column_field] || 0;
                            else if (row.consider_in_total_tax)
                                acc += row[column_field] || 0;

                            return acc;
                        }, 0);

                        return total;
                    },
                },
            },
            no_data_message: __("No data found"),
        });

        this.setup_datatable_listeners(treeView);
    }

    setup_datatable_listeners(isSummaryView) {
        const me = this;

        // Summary View
        if (isSummaryView) {
            this.datatable.$datatable.on("click", ".description", async function (e) {
                e.preventDefault();

                const summary_description = $(this).text();
                me.summary_view_callback &&
                    me.summary_view_callback(summary_description);
            });
            return;
        }

        // Detailed View
        this.instance.filter_fields.forEach(field => {
            this.datatable.$datatable.on("click", `.${field.fieldname}`, function (e) {
                e.preventDefault();

                const fieldname = field.fieldname;
                const value = $(this).text();
                me.detailed_view_callback &&
                    me.detailed_view_callback(fieldname, value);
            });
        });
    }

    setup_footer(wrapper) {
        const treeView = this.instance.active_view === "Summary";
        if (!treeView) {
            $(wrapper).find("[data-action=collapse_all_rows]").hide();
            $(wrapper).find("[data-action=expand_all_rows]").hide();
        } else {
            $(wrapper).find("[data-action=collapse_all_rows]").show();
            $(wrapper).find("[data-action=expand_all_rows]").hide();
        }

        this.setup_footer_actions(wrapper);
    }

    setup_footer_actions(wrapper) {
        const me = this;
        ["expand", "collapse"].forEach(action => {
            $(wrapper).on("click", `.${action}`, function (e) {
                e.preventDefault();
                me.datatable.datatable.rowmanager[`${action}AllNodes`]();
                $(wrapper).find("[data-action=collapse_all_rows]").toggle();
                $(wrapper).find("[data-action=expand_all_rows]").toggle();
            });
        });
    }

    set_creation_time_string() {
        const creation_time_string = this.get_creation_time_string();
        if (!creation_time_string) return;

        if ($(this.wrapper).find(".creation-time").length)
            $(this.wrapper).find(".creation-time").remove();

        this.wrapper
            .find(".report-footer")
            .append(
                `<div class="creation-time text-muted float-right">${creation_time_string}</div>`
            );
    }

    get_creation_time_string() {
        if (!this.data.creation) return;

        const creation = frappe.utils.to_title_case(
            frappe.datetime.prettyDate(this.data.creation)
        );

        return `Created ${creation}`;
    }

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

    remove_tab_custom_buttons() {
        this.wrapper.find(".custom-button-group").empty();
    }

    format_summary_table_cell(args) {
        const isDescriptionCell = args[1]?.id === "description";
        let value = args[0];

        if (args[1]?._fieldtype === "Currency") value = format_currency(value);
        else if (args[1]?._fieldtype === "Float") value = format_number(value);

        value =
            args[2]?.indent == 0
                ? `<strong>${value}</strong>`
                : isDescriptionCell
                ? `<a href="#" class="description">
                    <p style="padding-left: 15px">${value}</p>
                    </a>`
                    : value;

        return value;
    }

    format_detailed_table_cell(args) {
        /**
         * Update fieldname as a class to the cell
         * and make it clickable.
         *
         * This is used to simplify filtering of data
         */
        let value = frappe.format(...args);

        if (this.filter_fieldnames.includes(args[1]?.id))
            value = `
                <a href="#" class="${args[1]?.id}">
                    ${value}
                </a>`;

        return value;
    }

    get_icon(value, column, data, icon) {
        if (!data) return "";
        return `
        <button
            class="btn ${icon} reconcile-row"
            data-row-index='${data.idx}'
        >
            <i class="fa fa-${icon}"></i>
        </button>`;
    }
}

class GSTR1_TabManager extends TabManager {
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
                fieldname: "no_of_records",
                _fieldtype: "Float",
                width: 100,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                _fieldtype: "Float",
                width: 180,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataField.CGST,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataField.SGST,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
        ];
    }

    get_invoice_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer GSTIN",
                fieldname: GSTR1_DataField.CUST_GSTIN,
                width: 160,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            {
                name: "Reverse Charge",
                fieldname: GSTR1_DataField.REVERSE_CHARGE,
                width: 120,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            ...this.get_tax_columns(),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_export_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            {
                name: "Shipping Bill Number",
                fieldname: GSTR1_DataField.SHIPPING_BILL_NUMBER,
                width: 150,
            },
            {
                name: "Shipping Bill Date",
                fieldname: GSTR1_DataField.SHIPPING_BILL_DATE,
                width: 120,
            },
            {
                name: "Port Code",
                fieldname: GSTR1_DataField.SHIPPING_PORT_CODE,
                width: 100,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            ...this.get_igst_tax_columns(),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_document_columns(with_tax_rate) {
        // `Transaction Type` + Invoice Columns with `Document` as title instead of `Invoice`
        return [
            ...this.get_detail_view_column(),
            {
                name: "Transaction Type",
                fieldname: GSTR1_DataField.TRANSACTION_TYPE,
                width: 100,
            },
            {
                name: "Document Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Document Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer GSTIN",
                fieldname: GSTR1_DataField.CUST_GSTIN,
                width: 160,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            {
                name: "Document Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            {
                name: "Reverse Charge",
                fieldname: GSTR1_DataField.REVERSE_CHARGE,
                width: 120,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            ...this.get_tax_columns(with_tax_rate),
            {
                name: "Document Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_hsn_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "HSN Code",
                fieldname: GSTR1_DataField.HSN_CODE,
                width: 150,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Description",
                fieldname: GSTR1_DataField.DESCRIPTION,
                width: 300,
            },
            {
                name: "UOM",
                fieldname: GSTR1_DataField.UOM,
                width: 100,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            {
                name: "Total Quantity",
                fieldname: GSTR1_DataField.QUANTITY,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataField.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataField.CGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataField.SGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                fieldtype: "Float",
                width: 100,
            },
        ];
    }

    get_documents_issued_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Document Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 200,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            {
                name: "Sr No From",
                fieldname: GSTR1_DataField.FROM_SR,
                width: 150,
            },
            {
                name: "Sr No To",
                fieldname: GSTR1_DataField.TO_SR,
                width: 150,
            },
            {
                name: "Total Count",
                fieldname: GSTR1_DataField.TOTAL_COUNT,
                width: 120,
            },
            {
                name: "Draft Count",
                fieldname: GSTR1_DataField.DRAFT_COUNT,
                width: 120,
            },
            {
                name: "Cancelled Count",
                fieldname: GSTR1_DataField.CANCELLED_COUNT,
                width: 120,
            },
        ];
    }

    get_advances_received_columns() {
        return [
            ...this.get_detail_view_column(),
            ...this.get_match_columns(),
            ...this.get_tax_columns(true),
        ];
    }

    get_advances_adjusted_columns() {
        return [
            ...this.get_detail_view_column(),
            ...this.get_match_columns(),
            ...this.get_tax_columns(true),
        ];
    }

    // Common Columns

    get_tax_columns(with_tax_rate) {
        const columns = [
            {
                name: "Place of Supply",
                fieldname: GSTR1_DataField.POS,
                width: 150,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataField.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataField.CGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataField.SGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                fieldtype: "Float",
                width: 100,
            },
        ];

        if (!with_tax_rate) columns.splice(1, 1);

        return columns;
    }

    get_igst_tax_columns(with_pos) {
        const columns = [];

        if (with_pos)
            columns.push({
                name: "Place of Supply",
                fieldname: GSTR1_DataField.POS,
                width: 150,
                _value: (...args) => this.format_detailed_table_cell(args),
            });

        columns.push(
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataField.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                fieldtype: "Float",
                width: 100,
            }
        );

        return columns;
    }

    get_match_columns() {
        return [];
    }

    get_detail_view_column() {
        return [];
    }
}

class BooksTab extends GSTR1_TabManager {
    CATEGORY_COLUMNS = {
        // [GSTR1_Categories.NIL_EXEMPT]: this.get_document_columns,

        // SUBCATEGORIES
        [GSTR1_SubCategory.B2B_REGULAR]: this.get_invoice_columns,
        [GSTR1_SubCategory.B2B_REVERSE_CHARGE]: this.get_invoice_columns,
        [GSTR1_SubCategory.SEZWP]: this.get_invoice_columns,
        [GSTR1_SubCategory.SEZWOP]: this.get_invoice_columns,
        [GSTR1_SubCategory.DE]: this.get_invoice_columns,

        [GSTR1_SubCategory.EXPWP]: this.get_export_columns,
        [GSTR1_SubCategory.EXPWOP]: this.get_export_columns,

        [GSTR1_SubCategory.B2CL]: this.get_invoice_columns,
        [GSTR1_SubCategory.B2CS]: this.get_b2cs_columns,

        [GSTR1_SubCategory.NIL_EXEMPT]: this.get_nil_exempt_columns,

        [GSTR1_SubCategory.CDNR]: this.get_document_columns,
        [GSTR1_SubCategory.CDNUR]: this.get_document_columns,

        [GSTR1_SubCategory.AT]: this.get_advances_received_columns,
        [GSTR1_SubCategory.TXP]: this.get_advances_adjusted_columns,

        [GSTR1_SubCategory.HSN]: this.get_hsn_columns,

        [GSTR1_SubCategory.DOC_ISSUE]: this.get_documents_issued_columns,
    };

    DEFAULT_TITLE = "Summary of Books";

    setup_actions() {
        this.add_tab_custom_button("Download Excel", () =>
            this.download_books_as_excel()
        );
        this.add_tab_custom_button("Recompute", () => this.recompute_books());
    }

    filter_data(data, filters) {
        data = super.filter_data(data, filters);
        return data.filter(row => row.upload_status !== "Missing in Books");
    }

    // ACTIONS

    download_books_as_excel() {
        const url =
            "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_export.download_books_as_excel";

        open_url_post(`/api/method/${url}`, {
            company_gstin: this.instance.frm.doc.company_gstin,
            month_or_quarter: this.instance.frm.doc.month_or_quarter,
            year: this.instance.frm.doc.year,
        });
    }

    recompute_books() {
        render_empty_state(this.instance.frm);
        this.instance.frm.call("recompute_books");
    }

    // COLUMNS

    get_match_columns() {
        if (this.status === "Filed") return [];
        return [
            {
                name: "Upload Status",
                fieldname: GSTR1_DataField.UPLOAD_STATUS,
                width: 150,
            },
        ];
    }

    get_b2cs_columns() {
        let columns = this.get_document_columns(true);
        columns = columns.filter(
            col =>
                ![GSTR1_DataField.CUST_GSTIN, GSTR1_DataField.REVERSE_CHARGE].includes(
                    col.fieldname
                )
        );

        return columns;
    }

    get_nil_exempt_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Transaction Type",
                fieldname: GSTR1_DataField.TRANSACTION_TYPE,
                width: 100,
            },
            {
                name: "Document Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Document Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer GSTIN",
                fieldname: GSTR1_DataField.CUST_GSTIN,
                width: 160,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            {
                name: "Document Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            ...this.get_match_columns(),
            {
                name: "Nil-Rated Supplies",
                fieldname: GSTR1_DataField.NIL_RATED_AMOUNT,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "Exempted Supplies",
                fieldname: GSTR1_DataField.EXEMPTED_AMOUNT,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "Non-GST Supplies",
                fieldname: GSTR1_DataField.NON_GST_AMOUNT,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "Document Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_advances_received_columns() {
        return [
            {
                name: "Advance Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Payment Entry Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Payment Entry",
                width: 160,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            ...super.get_advances_received_columns(),
        ];
    }

    get_advances_adjusted_columns() {
        return [
            {
                name: "Adjustment Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Adjustment Entry Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            ...super.get_advances_adjusted_columns(),
        ];
    }
}

class FiledTab extends GSTR1_TabManager {
    CATEGORY_COLUMNS = {
        [GSTR1_SubCategory.B2B_REGULAR]: this.get_invoice_columns,
        [GSTR1_SubCategory.B2B_REVERSE_CHARGE]: this.get_invoice_columns,
        [GSTR1_SubCategory.SEZWP]: this.get_invoice_columns,
        [GSTR1_SubCategory.SEZWOP]: this.get_invoice_columns,
        [GSTR1_SubCategory.DE]: this.get_invoice_columns,

        [GSTR1_SubCategory.EXPWP]: this.get_export_columns,
        [GSTR1_SubCategory.EXPWOP]: this.get_export_columns,

        [GSTR1_SubCategory.B2CL]: this.get_b2cl_columns,
        [GSTR1_SubCategory.B2CS]: this.get_b2cs_columns,

        [GSTR1_SubCategory.NIL_EXEMPT]: this.get_nil_exempt_columns,

        [GSTR1_SubCategory.CDNR]: this.get_document_columns,
        [GSTR1_SubCategory.CDNUR]: this.get_cdnur_columns,

        [GSTR1_SubCategory.AT]: this.get_advances_received_columns,
        [GSTR1_SubCategory.TXP]: this.get_advances_adjusted_columns,

        [GSTR1_SubCategory.HSN]: this.get_hsn_columns,
        [GSTR1_SubCategory.DOC_ISSUE]: this.get_documents_issued_columns,
    };

    setup_actions() {
        this.add_tab_custom_button("Download Excel", () =>
            this.download_filed_as_excel()
        );

        if (this.status !== "Filed")
            this.add_tab_custom_button("Download JSON", () =>
                this.download_filed_json()
            );

        if (!is_gstr1_api_enabled()) return;

        if (this.status === "Filed")
            this.add_tab_custom_button("Sync with GSTN", () =>
                this.sync_with_gstn("filed")
            );
        else {
            this.add_tab_custom_button("Mark as Filed", () => this.mark_as_filed());
        }
    }

    set_default_title() {
        if (this.status === "Filed") this.DEFAULT_TITLE = "Summary of Filed GSTR-1";
        else this.DEFAULT_TITLE = "Summary of Draft GSTR-1";

        super.set_default_title();
    }

    // ACTIONS

    download_filed_as_excel() {
        const url =
            "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_export.download_filed_as_excel";

        open_url_post(`/api/method/${url}`, {
            company_gstin: this.instance.frm.doc.company_gstin,
            month_or_quarter: this.instance.frm.doc.month_or_quarter,
            year: this.instance.frm.doc.year,
        });
    }

    sync_with_gstn(sync_for) {
        render_empty_state(this.instance.frm);
        this.instance.frm.call("sync_with_gstn", { sync_for });
    }

    download_filed_json() {
        const me = this;
        function get_json_data(dialog) {
            const { include_uploaded, delete_missing } = dialog
                ? dialog.get_values()
                : {
                    include_uploaded: true,
                    delete_missing: false,
                };

            const doc = me.instance.frm.doc;

            frappe.call({
                method: "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_export.download_gstr_1_json",
                args: {
                    company_gstin: doc.company_gstin,
                    year: doc.year,
                    month_or_quarter: doc.month_or_quarter,
                    include_uploaded,
                    delete_missing,
                },
                callback: r => {
                    india_compliance.trigger_file_download(
                        JSON.stringify(r.message.data),
                        r.message.filename
                    );
                    dialog && dialog.hide();
                },
            });
        }

        // without API
        if (!is_gstr1_api_enabled()) {
            get_json_data();
            return;
        }

        // with API
        const dialog = new frappe.ui.Dialog({
            title: __("Download JSON"),
            fields: [
                {
                    fieldname: "include_uploaded",
                    label: __("Include Already Uploaded (matching) Invoices"),
                    description: __(
                        `This will include invoices already uploaded (and matching)
                         to GSTN (possibly e-Invoices) and overwrite them in GST Portal.
                         This is <strong>not recommended</strong> if e-Invoice is applicable to you
                         as it will overwrite the e-Invoice data in GST Portal.`
                    ),
                    fieldtype: "Check",
                },
                {
                    fieldname: "delete_missing",
                    label: __(
                        "Delete records that are missing in the Books from GST Portal"
                    ),
                    description: __(
                        "This will delete invoices that are not present in ERP but are present in GST Portal."
                    ),
                    fieldtype: "Check",
                    default: 1,
                },
            ],
            primary_action: () => get_json_data(dialog),
        });

        dialog.show();
    }

    mark_as_filed() {
        render_empty_state(this.instance.frm);
        this.instance.frm
            .call("mark_as_filed")
            .then(() => this.instance.frm.trigger("after_save"));
    }

    // COLUMNS

    get_b2cl_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            ...this.get_match_columns(),
            ...this.get_igst_tax_columns(true),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_b2cs_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 100,
            },
            ...this.get_tax_columns(true),
            ...this.get_match_columns(),
        ];
    }

    get_nil_exempt_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Description",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 200,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            {
                name: "Nil-Rated Supplies",
                fieldname: GSTR1_DataField.NIL_RATED_AMOUNT,
                fieldtype: "Currency",
                width: 150,
            },
            {
                name: "Exempted Supplies",
                fieldname: GSTR1_DataField.EXEMPTED_AMOUNT,
                fieldtype: "Currency",
                width: 150,
            },
            {
                name: "Non-GST Supplies",
                fieldname: GSTR1_DataField.NON_GST_AMOUNT,
                fieldtype: "Currency",
                width: 150,
            },
            {
                name: "Total Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_cdnur_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Transaction Type",
                fieldname: GSTR1_DataField.TRANSACTION_TYPE,
                width: 100,
            },
            {
                name: "Document Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Document Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            {
                name: "Document Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            ...this.get_match_columns(),
            ...this.get_igst_tax_columns(true),
            {
                name: "Document Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }
}

class UnfiledTab extends FiledTab {
    setup_actions() {
        if (!is_gstr1_api_enabled()) return;

        this.add_tab_custom_button("Sync with GSTN", () =>
            this.sync_with_gstn("unfiled")
        );
    }

    set_default_title() {
        this.DEFAULT_TITLE = "Summary of Invoices Uploaded on GST Portal";
        TabManager.prototype.set_default_title.call(this);
    }
}

class ReconcileTab extends FiledTab {
    DEFAULT_NO_DATA_MESSAGE = __("No differences found");

    set_default_title() {
        if (this.instance.data.status === "Filed")
            this.DEFAULT_TITLE = "Books vs Filed";
        else this.DEFAULT_TITLE = "Books vs Unfiled";

        this.DEFAULT_SUBTITLE = "Only differences";
        TabManager.prototype.set_default_title.call(this);
    }

    setup_actions() {
        this.add_tab_custom_button("Download Excel", () =>
            this.download_reconcile_as_excel()
        );
    }

    download_reconcile_as_excel() {
        const url =
            "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_export.download_reconcile_as_excel";

        open_url_post(`/api/method/${url}`, {
            company_gstin: this.instance.frm.doc.company_gstin,
            month_or_quarter: this.instance.frm.doc.month_or_quarter,
            year: this.instance.frm.doc.year,
        });
    }

    get_creation_time_string() { } // pass

    get_detail_view_column() {
        return [
            {
                fieldname: "detail_view",
                fieldtype: "html",
                width: 60,
                align: "center",
                _value: (...args) => this.get_icon(...args, "eye"),
            },
        ];
    }

    get_match_columns() {
        return [
            {
                name: "Match Status",
                fieldname: "match_status",
                width: 150,
            },
            {
                name: "Differences",
                fieldname: "differences",
                width: 150,
            },
        ];
    }
}

class DetailViewDialog {
    CURRENCY_FIELD_MAP = {
        [GSTR1_DataField.TAXABLE_VALUE]: "Taxable Value",
        [GSTR1_DataField.IGST]: "IGST",
        [GSTR1_DataField.CGST]: "CGST",
        [GSTR1_DataField.SGST]: "SGST",
        [GSTR1_DataField.CESS]: "CESS",
        [GSTR1_DataField.DOC_VALUE]: "Invoice Value",
    };

    IGNORED_FIELDS = [
        GSTR1_DataField.CUST_NAME,
        GSTR1_DataField.DOC_NUMBER,
        GSTR1_DataField.DOC_TYPE,
        "match_status",
        GSTR1_DataField.DESCRIPTION,
    ];

    constructor(data, field_label_map) {
        this.data = data;
        this.field_label_map = field_label_map;
        this.show_dialog();
    }

    show_dialog() {
        this.init_dialog();
        this.render_table();
        this.dialog.show();
    }

    init_dialog() {
        this.dialog = new frappe.ui.Dialog({
            title: "Detail View",
            fields: [
                {
                    fieldtype: "HTML",
                    fieldname: "reconcile_data",
                },
            ],
        });
    }

    render_table() {
        const detail_table = this.dialog.fields_dict.reconcile_data;
        const field_label_map = this.field_label_map.filter(
            field => !this.IGNORED_FIELDS.includes(field[0])
        );

        detail_table.html(
            frappe.render_template("gstr_1_detail_comparision", {
                data: this.data,
                fieldname_map: field_label_map,
                currency_map: this.CURRENCY_FIELD_MAP,
            })
        );
        this._set_value_color(detail_table.$wrapper, this.data);
    }

    _set_value_color(wrapper, data) {
        if (!Object.keys(data.gov).length || !Object.keys(data.books).length) return;

        let gov_data = data.gov;
        let books_data = data.books;

        for (const key in gov_data) {
            if (gov_data[key] === books_data[key] || key === "description") continue;

            wrapper
                .find(`[data-label='${key}'], [data-label='${key}']`)
                .addClass("not-matched");
        }
    }
}

// UTILITY FUNCTIONS
function is_gstr1_api_enabled() {
    return (
        india_compliance.is_api_enabled() &&
        !gst_settings.sandbox_mode &&
        gst_settings.compare_gstr_1_data
    );
}

function patch_set_indicator(frm) {
    frm.toolbar.set_indicator = function () { };
}

async function set_default_company_gstin(frm) {
    frm.set_value("company_gstin", "");

    const company = frm.doc.company;
    if (!company) return;

    const { message: gstin_list } = await frappe.call(
        "india_compliance.gst_india.utils.get_gstin_list",
        { party: company }
    );

    if (gstin_list && gstin_list.length) {
        frm.set_value("company_gstin", gstin_list[0]);
    }
}

function set_options_for_year(frm) {
    const today = new Date();
    const current_year = today.getFullYear();
    const start_year = 2017;
    const year_range = current_year - start_year + 1;
    let options = Array.from({ length: year_range }, (_, index) => start_year + index);
    options = options.reverse().map(year => year.toString());

    frm.get_field("year").set_data(options);
    frm.set_value("year", current_year.toString());
}

function set_options_for_month_or_quarter(frm) {
    /**
     * Set options for Month or Quarter based on the year and current date
     * 1. If the year is current year, then options are till current month
     * 2. If the year is 2017, then options are from July to December
     * 3. Else, options are all months or quarters
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
        if (frm.filing_frequency === "Monthly")
            options = india_compliance.MONTH.slice(0, current_month_idx + 1);
        else {
            let quarter_idx;
            if (current_month_idx <= 2) quarter_idx = 1;
            else if (current_month_idx <= 5) quarter_idx = 2;
            else if (current_month_idx <= 8) quarter_idx = 3;
            else quarter_idx = 4;

            options = india_compliance.QUARTER.slice(0, quarter_idx);
        }
    } else if (frm.doc.year === "2017") {
        // Options for 2017 from July to December
        if (frm.filing_frequency === "Monthly")
            options = india_compliance.MONTH.slice(6);
        else options = india_compliance.QUARTER.slice(2);
    } else {
        if (frm.filing_frequency === "Monthly") options = india_compliance.MONTH;
        else options = india_compliance.QUARTER;
    }

    set_field_options("month_or_quarter", options);
    if (frm.doc.year === current_year)
        // set second last option as default
        frm.set_value("month_or_quarter", options[options.length - 2]);
    // set last option as default
    else frm.set_value("month_or_quarter", options[options.length - 1]);
}

function render_empty_state(frm) {
    if ($(".gst-ledger-difference").length) {
        $(".gst-ledger-difference").remove();
    }
    frm.doc.__onload = null;
    frm.refresh();
}

async function get_net_gst_liability(frm) {
    const response = await frappe.call({
        method: "india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta.get_net_gst_liability",
        args: {
            month_or_quarter: frm.doc.month_or_quarter,
            year: frm.doc.year,
            company_gstin: frm.doc.company_gstin,
            company: frm.doc.company,
        },
    });

    return response?.message;
}
