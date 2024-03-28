// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

SUMMARY_COLUMNS = []
BOOKS_DETAILS_COLUMNS = {
    "b2b": [
        { label: "GSTIN/UIN of Recipient", fieldname: "gstin", fieldtype: "Data" },
        { label: "Invoice Number", fieldname: "invoice_no", fieldtype: "Data" },
    ]

}
FILED_DETAILS_COLUMNS = {
    "b2b": [
        { label: "GSTIN/UIN of Recipient", fieldname: "gstin", fieldtype: "Data" },
        { label: "Invoice Number", fieldname: "invoice_no", fieldtype: "Data" },
    ]
}

frappe.ui.form.on("GSTR-1 Beta", {
    setup(frm) {
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
    },

    before_save(frm) {
        frm.doc.__unsaved = true;
    },

    after_save(frm) {
        frm.gstr1.refresh(frm.doc.__onload?.data);
    },

    on_generate(frm) {
        frm.call("generate").then((r) => {
            if (!r.message) return;
            frm.doc._data = r.message;
            frm.trigger("set_indicator");
            frm.gstr1 = new GSTR1(frm);
        });
    },
});

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

class GSTR1 {
    // Render page / Setup Listeners / Setup Data
    TABS = [
        {
            label: __("Books"),
            views: ["Summary", "Details"],
            is_active: true,
            active_view: "Summary",
            actions: [{
                label: __("Download Excel"),
                action: () => this.download_books_as_excel(),
            }],
        }
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
        if (data)
            this.data = data;
    }

    // RENDER

    render() {
        this.render_tab_group();
        this.render_indicator();
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
                    fieldname: "filed_tab",
                    label: __("Filed"),
                },
                {
                    fieldtype: "HTML",
                    fieldname: "filed_html",
                }
            ],
            body: this.$wrapper,
            frm: this.frm,
        });
        this.tab_group.make();
    }

    render_indicator() {
        const status = this.frm.doc._data?.status;
        if (!status) return;

        let color = status === "Filed" ? "green" : "orange";
        frm.page.set_indicator(status, color);
    }

    // SETUP

    setup_tabs() {
        const tabs_html_wrapper = this.form.fields_dict.tabs_html.$wrapper;
        console.log(tabs_html_wrapper);
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
            ],
            body: tabs_html_wrapper,
            frm: { doctype: "GSTR1", get_perm: () => true, set_active_tab: () => { } },
        });
        this.tab_group.make();
    }

    // ACTIONS

    download_books_as_excel() { }

    // UTILS

    set_active_tab(tab) { }
}

class GSTR1Data {
    // Process Data / Summarize Data / Filter Data / Columns and Data Formatting / Reconcile
    constructor() { }

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
        this.active_view = this._views[0];
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

async function get_default_company_gstin(me) {
    me.form.set_value("company_gstin", "");

    const company = me.form.get_value("company");
    const { message: gstin_list } = await frappe.call(
        "india_compliance.gst_india.utils.get_gstin_list",
        { party: company }
    );

    if (gstin_list && gstin_list.length) {
        me.form.set_value("company_gstin", gstin_list[0]);
    }
}

function get_previous_month() {
    var previous_month_date = new Date();
    previous_month_date.setMonth(previous_month_date.getMonth() - 1);

    return previous_month_date.toLocaleDateString("en", { month: "long" });
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