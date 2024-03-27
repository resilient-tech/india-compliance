// {% include "india_compliance/public/js/purchase_reconciliation_tool/data_table_manager.js" %}
// {% include "india_compliance/public/js/purchase_reconciliation_tool/filter_group.js" %}

frappe.pages["gstr_1"].on_page_load = function (wrapper) {
    // TODO: add GSTR1 obj to india_compliance.gstr_1 ??
    india_compliance.gstr_1 = new GSTR1(wrapper);
};

// TODO: verify keys & values
const TYPES_OF_BUSINESS = {
    B2B: __("B2B Invoices - 4A, 4B, 4C, 6B, 6C"),
    B2CL: __("B2C(Large) Invoices - 5A, 5B"),
    B2CS: __("B2C(Small) Invoices - 7"),
    CDNR: __("Credit/Debit Notes (Registered) - 9B"),
    CDNUR: __("Credit/Debit Notes (Unregistered) - 9B"),
    EXP: __("Export Invoice - 6A"),
    TXP: __("Tax Liability (Advances Received) - 11A(1), 11A(2)"),
    AT: __("Adjustment of Advances - 11B(1), 11B(2)"),
    NIL: __("NIL RATED/EXEMPTED Invoices"),
    DOCISS: __("Document Issued Summary"),
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
        this._views = ["summary", "details"];
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
                    onchange: () => {
                        me.form.set_value("company_gstin", "");
                        this.render_empty_state();
                    },
                },
                {
                    fieldtype: "Column Break",
                },
                {
                    label: __("Company GSTIN"),
                    fieldname: "company_gstin",
                    fieldtype: "Autocomplete",
                    reqd: 1,
                    default: async () => {
                        await get_default_company_gstin(me);
                    },
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
        let generate_btn = this.page.set_primary_action("Generate", async () => {
            if (!this.form.get_values()) return;
            this.render_loading_state();

            await frappe.call({
                method: "india_compliance.gst_india.page.gstr_1.apis.get_mock_data",
                args: this.form.get_values(),
                callback: function (res) {
                    if (!res || !res.message) return;

                    me.gstr1_data.set_data(res.message);
                },
            });

            if (!this.generate_btn_clicked) {
                this.generate_btn_clicked = true;
            }
            // TODO: If filed_data present in response, set filed-green, else not_filed-red
            this.page.set_indicator("Filed", "green");

            this.render();
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
            const is_active = this.active_tab === tab ? "show active" : "";
            const data_table_per_view = this._views
                .map(view => {
                    return `<div id="gstr-1-__${tab}-${view}-data-table" class="dt"></div>`;
                })
                .join(" ");

            let tab_content = $(`
                <div class="tab-pane fade ${is_active}" id="gstr-1-__${tab}-content" role="tabpanel" aria-labelledby="gstr-1-__${tab}">
                    <div class="d-flex flex-row justify-content-between align-items-center" id="gstr-1-__${tab}-header">
                        <div class="view-heading ml-1" id="gstr-1-__${tab}-heading"></div>
                        <div class="tab-view-switch" id="gstr-1-__${tab}-custom-actions"></div>
                    </div>
                    <div id="gstr-1-__${tab}-data">
                        ${data_table_per_view}
                    </div>
                </div>
            `);
            this.tabs_content.append(tab_content);
            show_active_data_table(
                tab,
                "summary",
                tab_content.find(`#gstr-1-__${tab}-data`)
            );
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

            this._views.forEach(view => {
                const { columns, data } = this.gstr1_data.get_columns_and_data(
                    tab,
                    view
                );

                this.tabs[tab].datatable[view] = new india_compliance.DataTableManager({
                    $wrapper: $(`#gstr-1-__${tab}-${view}-data-table`),
                    columns: columns,
                    data: data,
                    options: {
                        cellHeight: 55,
                        serialNoColumn: view !== "summary",
                        noDataMessage: "No Data found!",
                    },
                });
            });
        });

        this.set_data_table_listeners();
    }

    set_data_table_listeners() {
        var me = this;
        this.tabs.books.datatable["summary"].$datatable.on(
            "click",
            ".section_name",
            async function (e) {
                e.preventDefault();

                const section_name = $(this).text();
                const active_tab = me.active_tab;
                const active_view = "details";

                // TODO: make dynamic
                me.tabs[active_tab].viewgroup.set_heading(section_name);
                me.tabs[active_tab].viewgroup.set_active_view(active_view);

                await me.filter_group.push_new_filter([
                    "GSTR-1",
                    "section_name",
                    "=",
                    section_name,
                ]);
                me.filter_group.apply();

                const { columns, data } = me.gstr1_data.get_columns_and_data(
                    active_tab,
                    active_view,
                    section_name
                );

                // TODO: refresh data-table with new data
                me.tabs[active_tab].datatable[active_view].refresh(data, columns);

                show_active_data_table(active_tab, active_view);
            }
        );
    }

    // CUSTOM TAB GROUP
    render_view_group() {
        this._tabs.forEach(tab => {
            this.tabs[tab].viewgroup = new ViewGroup({
                $wrapper: $(`#gstr-1-__${tab}-header`),
                tab: tab,
                _views: this._views,
                refresh: view => {
                    this.tabs[tab].datatable[view].refresh();
                },
            });
        });
    }

    // FILTER GROUP
    setup_filter_button() {
        this.filter_group = new india_compliance.FilterGroup({
            doctype: "GSTR-1", // TODO: technically wrong
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
        if (this.filter_group.filters.length === 0) {
            const current_tab = this.tabs[this.active_tab];
            const target_view = "summary";
            current_tab.datatable[target_view].refresh(
                this.gstr1_data.summary["books"]
            );
            current_tab.viewgroup.set_heading("");
            current_tab.viewgroup.set_active_view(target_view);

            show_active_data_table(this.active_tab, target_view);
        }
        // TODO: filter functionality
    }

    get_filter_fields() {
        // TODO: add more filters
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
        this.reset_data();
    }

    reset_data() {
        this.data = [];
        this.filtered_data = [];
        this.summary = {};
    }

    set_data(data) {
        this.data = data;

        // TODO: data cleaning & conversion
        this.generate_summary_data();

        this.filtered_data = this.data;
    }

    filter_data() {
        // TODO: apply necessary filters to the data
        // this.filtered_data = .....
    }

    generate_summary_data() {
        this.generate_books_summary_data();

        // TODO: generate all summary (not only books)
        // this.generate_filed_summary_data();
    }

    generate_books_summary_data() {
        const books_summary = [];

        for (const [section_name, section_data] of Object.entries(this.data)) {
            const section_summary = {
                section_name:
                    TYPES_OF_BUSINESS[section_name.toUpperCase()] ||
                    section_name.toUpperCase(),
                taxable_amount: 0,
                cgst: 0,
                sgst: 0,
                igst: 0,
                cess: 0,
            };

            section_data.forEach(inv => {
                section_summary.taxable_amount += inv.invoice_value;
                section_summary.cgst += inv.items[0].cgst_amount;
                section_summary.sgst += inv.items[0].sgst_amount;
                section_summary.igst += inv.items[0].igst_amount;
                section_summary.cess += inv.items[0].cess_amount;
            });

            books_summary.push(section_summary);
        }

        this.summary["books"] = books_summary;
    }

    generate_filed_summary_data() {
        // TODO: change function as per data
        const filed_summary = [];

        for (const [section_name, section_data] of Object.entries(this.data)) {
            const section_summary = {
                section_name: section_name,
                taxable_amount: 0,
                cgst: 0,
                sgst: 0,
                igst: 0,
                cess: 0,
            };

            section_data.forEach(inv => {
                section_summary.taxable_amount += inv.invoice_value;
                section_summary.cgst += inv.items[0].cgst_amount;
                section_summary.sgst += inv.items[0].sgst_amount;
                section_summary.igst += inv.items[0].igst_amount;
                section_summary.cess += inv.items[0].cess_amount;
            });

            filed_summary.push(section_summary);
        }

        this.summary["filed"] = filed_summary;
    }

    get_columns_and_data(tab, view, section_name = null) {
        // TODO: get cols & data acc to active tab & active view
        if (tab === "books") {
            if (view === "details") {
                if (!section_name) {
                    return { columns: [], data: [] };
                }
                return {
                    columns: this.get_books_section_wise_columns(section_name),
                    data: this.get_books_section_wise_data(section_name),
                };
            } else {
                return {
                    columns: this.get_books_summary_columns(),
                    data: this.summary[tab],
                };
            }
        }

        return { columns: [], data: [] };
    }

    get_books_summary_columns() {
        return [
            {
                name: "Section",
                fieldname: "section_name",
                width: 300,
                _value: (...args) => `<a href="#" class='section_name'>${args[0]}</a>`,
            },
            {
                name: "Taxable Amomunt",
                fieldname: "taxable_amount",
                width: 180,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "IGST",
                fieldname: "igst",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "CGST",
                fieldname: "cgst",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "SGST",
                fieldname: "sgst",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                name: "CESS",
                fieldname: "cess",
                width: 150,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
        ];
    }

    get_books_section_wise_data(section) {
        const section_key = Object.keys(TYPES_OF_BUSINESS).find(
            key => TYPES_OF_BUSINESS[key] == section
        );
        return this.data[section_key.toLowerCase()];
    }

    get_books_section_wise_columns(section) {
        // TODO: return section wise columns
        return this.get_b2b_columns();
    }

    get_b2b_columns() {
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

function show_active_data_table(active_tab, active_view, target_div = null) {
    if (!target_div) target_div = $(`#gstr-1-__${active_tab}-data`);

    target_div.children().filter(".dt").hide();
    target_div.find(`#gstr-1-__${active_tab}-${active_view}-data-table`).show();
}
