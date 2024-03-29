// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

DOCTYPE = "GSTR-1 Beta";

SUMMARY_COLUMNS = [];
BOOKS_DETAILS_COLUMNS = {
    b2b: [
        { label: "GSTIN/UIN of Recipient", fieldname: "gstin", fieldtype: "Data" },
        { label: "Invoice Number", fieldname: "invoice_no", fieldtype: "Data" },
    ],
};
FILED_DETAILS_COLUMNS = {
    b2b: [
        { label: "GSTIN/UIN of Recipient", fieldname: "gstin", fieldtype: "Data" },
        { label: "Invoice Number", fieldname: "invoice_no", fieldtype: "Data" },
    ],
};

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        patch_set_active_tab(frm);
        await set_default_fields(frm);

        await frappe.require("gstr1.bundle.js");
        frm.gstr1 = new GSTR1(frm);
    },

    async company(frm) {
        if (!frm.doc.company) return;
        const options = await set_gstin_options(frm);

        frm.set_value("company_gstin", options[0]);
    },

    refresh(frm) {
        // Primary Action
        frm.disable_save();
        frm.page.set_primary_action(__("Generate"), () => frm.save());

        frm.add_custom_button("Download Excel", () => {});

        // // move actions button next to filters
        // for (let button of $(".custom-actions")) {
        //     $(".custom-button-group").remove();
        //     $(button).appendTo($(".custom-button-group"));
        // }
    },

    before_save(frm) {
        frm.doc.__unsaved = true;
    },

    after_save(frm) {
        frm.gstr1.refresh(frm.doc.__onload?.data);
    },
});

class GSTR1 {
    // Render page / Setup Listeners / Setup Data
    TABS = [
        {
            label: __("Books"),
            name: "books",
            views: ["Summary", "Details"],
            is_active: true,
            active_view: "Summary",
            actions: [
                {
                    label: __("Download Excel"),
                    action: () => this.download_books_as_excel(),
                },
            ],
        },
        {
            label: __("Reconcile"),
            name: "reconcile",
            views: ["Summary", "Details"],
            is_active: false,
            active_view: "Summary",
        },
        {
            label: __("Filed"),
            name: "filed",
            views: ["Summary", "Details"],
            is_active: false,
            active_view: "Summary",
            actions: [
                {
                    label: __("Mark as Filed"),
                    action: () => this.mark_as_filed(),
                },
            ],
        },
    ];

    constructor(frm) {
        this.init(frm);
        this.render();
    }

    init(frm) {
        this.frm = frm;
        this.data = frm.doc._data;
        this.$wrapper = frm.fields_dict.tabs_html.$wrapper;
    }

    refresh(data) {
        if (data) {
            this.data = data;
            this.refresh_filter_fields();
        }

        // apply filters
    }

    // RENDER

    render() {
        this.render_tab_group();
        this.render_indicator();
        this.setup_filter_button();
        this.render_view_groups();
        this.render_data_tables();
    }

    render_tab_group() {
        this.tab_group = new frappe.ui.FieldGroup({
            fields: [
                {
                    //hack: for the FieldGroup(Layout) to avoid rendering default "details" tab
                    fieldtype: "Section Break",
                },
                {
                    fieldtype: "Tab Break",
                    fieldname: "books_tab",
                    label: __("Books"),
                    active: 1,
                },
                {
                    fieldtype: "HTML",
                    fieldname: "books_html",
                },
                {
                    fieldtype: "Tab Break",
                    fieldname: "reconcile_tab",
                    label: __("Reconcile"),
                },
                {
                    fieldtype: "HTML",
                    fieldname: "reconcile_html",
                },
                {
                    fieldtype: "Tab Break",
                    fieldname: "filed_tab",
                    label: __("Filed"),
                },
                {
                    fieldtype: "HTML",
                    fieldname: "filed_html",
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

    render_indicator() {
        const status = this.frm.doc._data?.status;
        if (!status) return;

        let color = status === "Filed" ? "green" : "orange";
        frm.page.set_indicator(status, color);
    }

    render_view_groups() {
        // this.TABS.forEach(tab => {
        //     this.tabs[`${tab.name}_tab`].viewgroup = new ViewGroup({
        //         $wrapper: "",
        //         tab: tab.name,
        //         _views: tab.views,
        //         active_view: tab.active_view,
        //     });
        // });
    }

    render_data_tables() {
        this.TABS.forEach(tab => {
            this.tabs[`${tab.name}_tab`].datatable = new india_compliance.DataTableManager({
                $wrapper: this.tab_group.get_field(`${tab.name}_html`).$wrapper,
                columns: [],
                data: [],
                options: {
                    cellHeight: 55,
                },
            });
        });
        this.set_datatable_listeners();
    }

    // SETUP

    setup_filter_button() {
        this.filter_group = new india_compliance.FilterGroup({
            doctype: DOCTYPE,
            parent: this.$wrapper.find(".form-tabs-list"),
            filter_options: {
                fieldname: "section_name",
                filter_fields: this.get_filter_fields(),
            },
            on_change: () => {
                this.refresh();
            },
        });
    }

    // LISTENERS

    set_datatable_listeners() {
        const me = this;
        this.tabs.books_tab.datatable.$datatable.on("click", ".match-status", async function (e) {
            e.preventDefault();

            const match_status = $(this).text();
            await me.filter_group.push_new_filter([
                DOCTYPE,
                "match_status",
                "=",
                match_status,
            ]);
            me.filter_group.apply();
        });
    }

    // ACTIONS

    download_books_as_excel() {}

    mark_as_filed() {}

    // UTILS

    get_filter_fields() {
        const fields = [
            {
                label: "Section Name",
                fieldname: "section_name",
                fieldtype: "Autocomplete",
                options: ["B2B", "B2CL", "B2CS"],
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

    apply_filters() {}
}

class GSTR1Data {
    // Process Data / Summarize Data / Filter Data / Columns and Data Formatting / Reconcile
    constructor() {}

    reset_data() {
        this.data = {}; // Raw Data
        this.filtered_data = {}; // Filtered Data / Details View
        this.summary = {}; // Summary Data
    }
}

class TabManager {
    //
}

class ViewGroup {
    constructor(options) {
        Object.assign(this, options);
        this.views = {};
        this.heading = this.$wrapper.find(".view-heading");
        this.render();
    }

    set_heading(text) {
        this.heading.html(`<h4>${text}</h4>`);
    }

    set_active_view(view) {
        this.active_view = view;
        this.views[`${view}_view`].children().tab("show");
    }

    render() {
        this.tab_link_container = $(`
            <ul class="nav custom-tabs rounded-sm border d-inline-flex mb-3" id="custom-tabs" role="tablist"></ul>
		`).appendTo(this.$wrapper.find(".tab-view-switch"));

        this.make_views();
        this.setup_view_events();
    }

    make_views() {
        this._views.forEach(view => {
            this.views[`${view}_view`] = $(`<li class="nav-item show">
                <a
                    class="nav-link ${this.active_view === view ? "active" : ""}"
                    id="gstr-1-__${view}-view"
                    data-toggle="tab"
                    data-fieldname="${view}"
                    href="#gstr-1-__${view}-view"
                    role="tab"
                    aria-controls="gstr-1-__${view}-view"
                    aria-selected="true"
                >
                    ${frappe.unscrub(view)}
                </a>
            </li>`).appendTo(this.tab_link_container);
        });
    }

    setup_view_events() {
        this.tab_link_container.off("click").on("click", ".nav-link", e => {
            e.preventDefault();
            e.stopImmediatePropagation();

            const $target = $(e.currentTarget);
            $target.tab("show");

            this.active_view = $target.attr("data-fieldname");
            show_active_data_table(this.tab, this.active_view);
            // this.refresh(this.active_view);
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

async function set_gstin_options(frm) {
    const { query, params } = india_compliance.get_gstin_query(frm.doc.company);
    const { message } = await frappe.call({
        method: query,
        args: params,
    });

    if (!message) return [];
    const gstin_field = frm.get_field("company_gstin");
    gstin_field.set_data(message);
    return message;
}

async function set_default_fields(frm) {
    await set_default_company_gstin(frm);
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