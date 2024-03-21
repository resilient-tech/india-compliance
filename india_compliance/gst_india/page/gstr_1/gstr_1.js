// {% include "india_compliance/public/js/purchase_reconciliation_tool/data_table_manager.js" %}
// {% include "india_compliance/public/js/purchase_reconciliation_tool/filter_group.js" %}

frappe.pages["gstr_1"].on_page_load = function (wrapper) {
    // TODO: add GSTR1 obj to india_compliance.gstr_1 ??
    india_compliance.gstr_1 = new GSTR1(wrapper);
};

// TODO: either import from report/gstr_1.js or vice versa
const TYPES_OF_BUSINESS = {
    B2B: __("B2B Invoices - 4A, 4B, 4C, 6B, 6C"),
    "B2C Large": __("B2C(Large) Invoices - 5A, 5B"),
    "B2C Small": __("B2C(Small) Invoices - 7"),
    "CDNR-REG": __("Credit/Debit Notes (Registered) - 9B"),
    "CDNR-UNREG": __("Credit/Debit Notes (Unregistered) - 9B"),
    EXPORT: __("Export Invoice - 6A"),
    Advances: __("Tax Liability (Advances Received) - 11A(1), 11A(2)"),
    Adjustment: __("Adjustment of Advances - 11B(1), 11B(2)"),
    "NIL Rated": __("NIL RATED/EXEMPTED Invoices"),
    "Document Issued Summary": __("Document Issued Summary"),
    HSN: __("HSN-wise-summary of outward supplies"),
};

class GSTR1 {
    constructor(wrapper) {
        this.$wrapper = wrapper;
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: "GSTR-1",
            single_column: true,
            card_layout: true,
        });
        this.setup_page();
    }

    setup_page() {
        this._tabs = ["books", "reconcile", "filed"]; // primary tabs
        this.tab_views = {
            books: ["Summary", "Invoice", "HSN"],
            reconcile: ["Summary", "Details"],
            filed: ["Summary", "Details"],
        };
        this.tab_actions = {
            books: [
                {
                    label: "Download Excel",
                    callback: () => {},
                },
            ],
            reconcile: [],
            filed: [
                {
                    label: "Mark as Filed",
                    callback: () => {},
                },
            ],
        };
        this.tabs = Object.fromEntries(this._tabs.map(tab => [tab, {}]));
        this.gstr1_data = new GSTR1Data();

        // TODO: set status dynamically from GSTR filed log
        this.page.set_indicator("Not Filed", "red");

        this.make_page_actions();
        this.make_form();
        this.render();
    }

    make_form() {
        var me = this;
        var current_date = new Date();
        this.form = new frappe.ui.FieldGroup({
            fields: [
                {
                    fieldtype: "Section Break",
                    fieldname: "section-filters",
                },
                {
                    label: __("Company"),
                    fieldname: "company",
                    fieldtype: "Link",
                    options: "Company",
                    reqd: 1,
                    default: frappe.defaults.get_user_default("Company"),
                    onchange: () => this.render_empty_state(),
                },
                {
                    fieldtype: "Column Break",
                },
                {
                    label: __("Company GSTIN"),
                    fieldname: "company_gstin",
                    fieldtype: "Autocomplete",
                    reqd: 1,
                    default: get_company_default_gstin(),
                    get_query: () => {
                        const company = me.form.get_value("company");

                        return company
                            ? india_compliance.get_gstin_query(company)
                            : null;
                    },
                    onchange: () => this.render_empty_state(),
                },
                {
                    fieldtype: "Column Break",
                },
                {
                    label: __("Month"),
                    fieldname: "month",
                    fieldtype: "Select",
                    reqd: 1,
                    default: get_previous_month(),
                    options:
                        "January\nFebruary\nMarch\nApril\nMay\nJune\nJuly\nAugust\nSeptember\nOctober\nNovember\nDecember",
                    onchange: () => this.render_empty_state(),
                },
                {
                    fieldtype: "Column Break",
                },
                {
                    label: __("Year"),
                    fieldname: "year",
                    fieldtype: "Autocomplete",
                    reqd: 1,
                    default: current_date.getFullYear().toString(),
                    options: get_year_list(current_date),
                    onchange: () => this.render_empty_state(),
                },
                {
                    fieldtype: "Section Break",
                    fieldname: "tab-section",
                },
            ],
            body: this.page.body,
        });
        this.form.make();
    }

    render() {
        this.tab_section = $(
            ".form-page [data-fieldname='tab-section'] > .section-body"
        )
            .empty()
            .addClass("d-flex flex-column rounded-sm border m-3");

        this.tab_section.parent().removeClass("empty-section");

        // TODO: replace condition with this.gstr1_data.has_data or something similar
        this.generate_btn_clicked ? this.render_content() : this.render_empty_state();
    }

    render_empty_state() {
        this.tab_section.empty().append(
            `<div class="gstr-1-no-data-state">
				<div class="no-result text-center">
					<img src="/assets/frappe/images/ui-states/search-empty-state.svg" alt="Empty State" class="null-state">
					<div class="state-text">Click <b>Generate</b> to view report</div>
				</div>
			</div>`
        );
    }

    render_loading_state() {
        this.tab_section.empty().append(
            `<div class="gstr-1-loading-state">
				<div class="no-result text-center">
					<div class="state-text">Fetching your data...</div>
				</div>
			</div>`
        );
    }

    make_page_actions() {
        var me = this;
        let generate_btn = this.page.set_primary_action("Generate", () => {
            if (!this.form.get_values()) return;

            this.render_loading_state();

            // TODO: add api call here
            setTimeout(() => {
                if (!this.generate_btn_clicked) {
                    this.generate_btn_clicked = true;
                }
                this.render();
            }, 1000);
        });

        // TODO: Add more actions as required
        let download_btn = this.page.set_secondary_action("Download GSTR", () => {});
        let menu_btn = this.page.add_menu_item("Actions", () => {}, true);
    }

    render_content() {
        this.active_tab = this._tabs[0];

        $(`
			<div class="form-tabs-list d-flex flex-row justify-content-between">
				<ul class="nav form-tabs" id="form-tabs" role="tablist">
					${this.make_tabs()}
				</ul>
                <div class="tab-actions">
                    <div class="view-btn-grp"></div>
                    <div class="filter-grp"></div>
                </div>
			</div>
		`).appendTo(this.tab_section);

        this.tab_link_container = this.tab_section.find(".form-tabs");
        this.tab_actions_container = this.tab_section.find(".tab-actions");

        this.make_tab_actions();
        this.setup_tab_events();
        this.setup_filter_button();
        this.setup_tab_content();
    }

    // TABS
    make_tabs() {
        return this._tabs
            .map(tab => {
                return `<li class="nav-item show">
                <a
                    class="nav-link ${this.active_tab === tab ? "active" : ""}"
                    id="gstr-1-__${tab}"
                    data-toggle="tab"
                    data-fieldname="${tab}"
                    href="#gstr-1-__${tab}"
                    role="tab"
                    aria-controls="gstr-1-__${tab}"
                    aria-selected="true"
                >
                    ${frappe.unscrub(tab)}
                </a>
            </li>`;
            })
            .join(" ");
    }

    make_tab_actions() {
        const btn_group_div = this.tab_actions_container.find(".view-btn-grp").empty();

        this.tab_actions[this.active_tab].forEach(action => {
            const btn = $("<button>")
                .addClass("ml-2 btn btn-secondary btn-sm")
                .attr("data-label", frappe.scrub(action.label))
                .text(action.label)
                .on("click", action.callback);

            btn_group_div.append(btn);
        });
    }

    setup_tab_events() {
        this.tab_link_container.off("click").on("click", ".nav-link", e => {
            e.preventDefault();
            e.stopImmediatePropagation();
            $(e.currentTarget).tab("show");

            // Extract active tab and update tab content
            this.active_tab = $(e.currentTarget).attr("data-fieldname");
            this.update_tab_actions_and_content();
        });
    }

    setup_tab_content() {
        this.tabs_content = $(
            `<div class="form-tab-content tab-content m-3"></div>`
        ).appendTo(this.tab_section);

        this._tabs.forEach(tab => {
            let tab_content = $(`
                <div
                    class="tab-pane fade ${
                        this.active_tab === tab ? "show active" : ""
                    }"
                    id="gstr-1-__${tab}-content"
                    role="tabpanel"
                    aria-labelledby="gstr-1-__${tab}"
                >
                    <div class="d-flex flex-row justify-content-between align-items-center" id="gstr-1-__${tab}-header">
                        <div class="view-heading ml-1" id="gstr-1-__${tab}-heading"></div>
                        <div class="tab-view-switch" id="gstr-1-__${tab}-custom-actions"></div>
                    </div>
                    <div id="gstr-1-__${tab}-data">
                    ${this.tab_views[tab]
                        .map(view => {
                            return `<div id="gstr-1-__${tab}-${view}-data-table" class="dt"></div>`;
                        })
                        .join(" ")}
                    </div>
                </div>
            `);
            this.tabs_content.append(tab_content);
            toggle_data_table_visibility(tab, "Summary");
        });
        this.render_view_group();
        this.render_data();
    }

    update_tab_actions_and_content() {
        // find all tabs-content & remove `show active` class
        this.tabs_content.find(".tab-pane").removeClass("show active");

        // add `show active` class to current tab
        this.tabs_content
            .find(`#gstr-1-__${this.active_tab}-content`)
            .addClass("show active");

        this.make_tab_actions();
    }

    // DATA TABLE
    render_data() {
        this._tabs.forEach(tab => {
            this.tabs[tab].datatable = {};

            this.tab_views[tab].forEach((view, index) => {
                this.tabs[tab].datatable[view] = new india_compliance.DataTableManager({
                    $wrapper: $(`#gstr-1-__${tab}-${view}-data-table`),
                    columns: this.gstr1_data.get_books_overview_columns(),
                    data: this.gstr1_data.get_books_overview_data(),
                    options: {
                        cellHeight: 55,
                        serialNoColumn: index !== 0, // Remove serialNoColumn for Summary view
                        noDataMessage: "No Data found!",
                    },
                });
            });
        });

        this.set_data_table_listeners();
    }

    set_data_table_listeners() {
        var me = this;
        this.tabs.books.datatable["Summary"].$datatable.on(
            "click",
            ".section_name",
            async function (e) {
                e.preventDefault();

                const section_name = $(this).text();

                // TODO: make dynamic
                me.tabs.books.viewgroup.set_heading(section_name);
                me.tabs.books.viewgroup.set_active_view("Invoice");

                await me.filter_group.push_new_filter([
                    "GSTR-1",
                    "section_name",
                    "=",
                    section_name,
                ]);
                me.filter_group.apply();

                // TODO: refresh data-table with new data
                // me.tabs[me.active_tab].datatable.refresh(
                //     me.gstr1_data.get_books_section_wise_data(section_name)
                // );
            }
        );
    }

    // CUSTOM TAB GROUP
    render_view_group() {
        this._tabs.forEach(tab => {
            this.tabs[tab].viewgroup = new ViewGroup({
                $wrapper: $(`#gstr-1-__${tab}-header`),
                tab: tab,
                _views: this.tab_views[tab],
                refresh: view => {
                    this.tabs[tab].datatable[view].refresh();
                },
            });
        });
    }

    // FILTER GROUP
    setup_filter_button() {
        this.filter_group = new india_compliance.FilterGroup({
            doctype: "GSTR-1",
            parent: this.tab_actions_container.find(".filter-grp"),
            filter_options: {
                fieldname: "section_name",
                filter_fields: this.get_filter_fields(),
            },
            on_change: () => {
                // TODO: dont apply filters if filters are unchanged

                this.apply_filters();
            },
        });
    }

    apply_filters() {
        // if (this.filter_group.filters.length === 0) {
        //     const current_tab = this.tabs[this.active_tab];
        //     current_tab.datatable.refresh(this.gstr1_data.get_books_overview_data());
        //     current_tab.viewgroup.set_heading("");
        //     current_tab.viewgroup.set_active_view("Summary");
        // }
        // TODO: filter functionality
    }

    get_filter_fields() {
        return [
            {
                label: "Section Name",
                fieldname: "section_name",
                fieldtype: "Autocomplete",
                options: Object.keys(TYPES_OF_BUSINESS).map(
                    key => TYPES_OF_BUSINESS[key]
                ),
                parent: "GSTR-1",
            },
        ];
    }
}

class GSTR1Data {
    constructor() {
        this.books_data = {
            Overview: Object.keys(TYPES_OF_BUSINESS).map(key => {
                return [TYPES_OF_BUSINESS[key], "10", "3000", "9", "9", "0"];
            }),
            B2B: [
                ["SINV-001", "default description", "3000", "3000", "9", "9", "0"],
                ["SINV-002", "description", "3000", "3000", "9", "9", "0"],
                ["SINV-003", "default", "3000", "3000", "9", "9", "0"],
                ["SINV-004", "defaucription", "3000", "3000", "9", "9", "0"],
                ["SINV-005", "defaulion", "3000", "3000", "9", "9", "0"],
                ["SINV-001", "default description", "3000", "3000", "9", "9", "0"],
                ["SINV-002", "description", "3000", "3000", "9", "9", "0"],
                ["SINV-003", "default", "3000", "3000", "9", "9", "0"],
                ["SINV-004", "defaucription", "3000", "3000", "9", "9", "0"],
                ["SINV-005", "defaulion", "3000", "3000", "9", "9", "0"],
            ],
            "B2C Large": [],
            "B2C Small": [],
            "CDNR-REG": [],
            "CDNR-UNREG": [],
            EXPORT: [],
            Advances: [],
            Adjustment: [],
            "NIL Rated": [],
            "Document Issued Summary": [],
            HSN: [],
        };
    }

    get_columns_and_data(active_tab, active_view) {
        return { columns: [], data: [] };
    }

    get_books_overview_columns() {
        return [
            {
                label: "Section",
                fieldname: "section_name",
                width: 300,
                _value: (...args) => `<a href="#" class='section_name'>${args[0]}</a>`,
            },
            {
                label: "Total Transactions",
                fieldname: "total_txns",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Taxable Amomunt",
                fieldname: "taxable_amount",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "IGST",
                fieldname: "igst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "CGST",
                fieldname: "cgst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "SGST",
                fieldname: "sgst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
        ];
    }

    get_books_overview_data() {
        return this.books_data.Overview;
    }

    get_books_section_wise_data(section) {
        const section_key = Object.keys(TYPES_OF_BUSINESS).find(
            key => TYPES_OF_BUSINESS[key] == section
        );
        return this.books_data[section_key];
    }

    get_b2b_overview_columns() {
        return [
            {
                label: "Section",
                fieldname: "section_name",
                width: 150,
                _value: (...args) => `<a href="#" class='section_name'>${args[0]}</a>`,
            },
            {
                label: "Description",
                fieldname: "description",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Total Amomunt",
                fieldname: "total_amount",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Taxable Amomunt",
                fieldname: "taxable_amount",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "IGST",
                fieldname: "igst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "CGST",
                fieldname: "cgst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "SGST",
                fieldname: "sgst",
                width: 100,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
        ];
    }
}

class ViewGroup {
    constructor(options) {
        Object.assign(this, options);
        this.views = {};
        this.active_view = frappe.scrub(this._views[0]);
        this.heading = this.$wrapper.find(".view-heading");
        this.render();
    }

    set_heading(text) {
        this.heading.html(`<h4>${text}</h4>`);
    }

    set_active_view(tab) {
        tab = frappe.scrub(tab);
        this.active_view = tab;
        this.views[`${tab}_view`].children().tab("show");
    }

    render() {
        this.tab_link_container = $(`
            <ul class="nav custom-tabs rounded-sm border d-inline-flex mb-3" id="custom-tabs" role="tablist"></ul>
		`).appendTo(this.$wrapper.find(".tab-view-switch"));

        this.make_views();
        this.setup_view_events();
    }

    make_views() {
        this._views.forEach(tab => {
            let _view = frappe.scrub(tab);
            this.views[`${_view}_view`] = $(`<li class="nav-item show">
                <a
                    class="nav-link ${this.active_view === _view ? "active" : ""}"
                    id="gstr-1-__${_view}-view"
                    data-toggle="tab"
                    data-fieldname="${tab}"
                    href="#gstr-1-__${_view}-view"
                    role="tab"
                    aria-controls="gstr-1-__${_view}-view"
                    aria-selected="true"
                >
                    ${tab}
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

            // TODO: toggle data-table visibility
            toggle_data_table_visibility(this.tab, this.active_view);
            this.refresh(this.active_view);
        });
    }
}

function get_company_default_gstin() {
    // TODO
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

function toggle_data_table_visibility(active_tab, active_view) {
    const tab_data_div = $(`#gstr-1-__${active_tab}-data`);
    tab_data_div.children().filter(".dt").hide();
    tab_data_div.find(`#gstr-1-__${active_tab}-${active_view}-data-table`).show();
}
