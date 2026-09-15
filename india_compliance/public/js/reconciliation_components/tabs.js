frappe.provide("reconciliation");

// what each match type covers, shown on hover. key order is the order they are listed in
const MATCH_STATUS_INFO = {
    "Exact Match": __("Bill no, GSTIN, place of supply, reverse charge and every tax amount are the same."),
    "Suggested Match": __(
        "Same invoice with small gaps. Bill no is close, or tax amounts differ by up to 1 rupee.",
    ),
    Mismatch: __(
        "Same supplier and fiscal year, but the two disagree on bill no, GSTIN, place of supply, reverse charge or tax amounts.",
    ),
    "Manual Match": __("You linked these two documents yourself."),
    "Only in 2A/2B": __("Supplier has reported it. Not in your books."),
    "Only in Books": __("You have booked it. Supplier has not reported it in 2A/2B."),
    "Suggested Mark as Pending": __("Belongs to a later period. Keep it pending and claim it then."),
};

function get_gstin_status_at_invoice_date(row) {
    if (
        row.gstin_status === "Cancelled" &&
        row.gstin_cancelled_date &&
        row.bill_date &&
        frappe.datetime.str_to_obj(row.bill_date) < frappe.datetime.str_to_obj(row.gstin_cancelled_date)
    ) {
        return "Active";
    }
    return row.gstin_status;
}

function get_gstin_indicator_color(status) {
    if (status === "Active") return "green";
    if (status === "Cancelled") return "red";
    if (status === "Suspended") return "orange";
    return "grey";
}

reconciliation.reconciliation_tabs = class ReconciliationTabs {
    // summary tab -> how its rows pick invoices. set by each tool
    summary_matchers = {};

    constructor(frm, tabs, data_field) {
        this.frm = frm;
        this.data = [];
        this._tabs = tabs;
        this.$wrapper = frm.get_field(data_field).$wrapper.addClass("gst-return-tabs");
        frm.$wrapper.addClass("gst-return-tool");

        this.render_tab_group();
        this.setup_filter_button(frm.doctype);
    }

    render_data(data) {
        this.data = data;
        this.filtered_data = data;

        this.apply_filters(true);

        this.render_data_tables();
        this.refresh_filter_fields();
    }

    refresh(data) {
        if (data) {
            this.data = data;
            this.refresh_filter_fields();
        }

        this.apply_filters(!!data);

        // data unchanged!
        if (this.rendered_data == this.filtered_data) return;

        this._tabs.forEach((tab) => {
            this.tabs[`${tab}_tab`].datatable?.refresh(this[`get_${tab}_data`]());
        });

        this.rendered_data = this.filtered_data;
    }

    render_tab_group() {
        const fields = this.get_tab_group_fields();

        this.tab_group = new frappe.ui.FieldGroup({
            fields,
            body: this.$wrapper,
            frm: this.frm,
        });

        this.tab_group.make();

        // make tabs_dict for easy access
        this.tabs = Object.fromEntries(this.tab_group.tabs.map((tab) => [tab.df.fieldname, tab]));
    }

    get_tab_group_fields() {
        return [];
    }

    setup_filter_button(doctype) {
        this.filter_group = new india_compliance.FilterGroup({
            doctype,
            parent: this.$wrapper.find(".form-tabs-list"),
            filter_options: {
                fieldname: "supplier_name",
                filter_fields: this.get_filter_fields(),
            },
            on_change: () => {
                this.refresh();
            },
        });
    }

    get_filter_fields() {
        const fields = [];
        const dimension_fields = this.get_accounting_dimensions();

        dimension_fields.forEach((dimension) => {
            const label = frappe.unscrub(dimension);
            fields.push({
                label,
                fieldname: dimension,
                fieldtype: "Autocomplete",
                options: this.get_autocomplete_options(dimension),
            });
        });

        return fields;
    }

    apply_filters(force, supplier_filter) {
        const has_filters = this.filter_group.filters.length > 0 || supplier_filter;
        if (!has_filters) {
            this.filters = null;
            this.filtered_data = this.data;
            return;
        }

        let filters = this.filter_group.get_filters();
        if (supplier_filter) filters.push(supplier_filter);
        if (!force && this.filters === filters) return;

        this.filters = filters;
        this.filtered_data = this.data.filter((row) => {
            return filters.every((filter) =>
                india_compliance.FILTER_OPERATORS[filter[2]](filter[3] || "", row[filter[1]] || ""),
            );
        });
    }

    refresh_filter_fields() {
        this.filter_group.filter_options.filter_fields = this.get_filter_fields();
    }

    get_autocomplete_options(field) {
        const options = [];
        this.data.forEach((row) => {
            if (row[field] && !options.includes(row[field])) options.push(row[field]);
        });
        return options;
    }

    render_data_tables() {
        this._tabs.forEach((tab) => {
            this.tabs[`${tab}_tab`].datatable = new india_compliance.DataTableManager({
                $wrapper: this.tab_group.get_field(`${tab}_data`).$wrapper,
                columns: this[`get_${tab}_columns`](),
                data: this[`get_${tab}_data`](),
                options: {
                    cellHeight: 55,
                },
            });
        });
        this.set_listeners();
    }

    // holds a column in a fixed order, anything unlisted goes last
    sort_by_order(rows, field, order) {
        const rank = (value) => {
            const index = order.indexOf(value);
            return index === -1 ? order.length : index;
        };

        return rows.sort((a, b) => rank(a[field]) - rank(b[field]));
    }

    // every tab lists match statuses in the same order
    sort_by_match_status(rows) {
        return this.sort_by_order(rows, "match_status", Object.keys(MATCH_STATUS_INFO));
    }

    // supplier and document tabs go by gstin, then oldest bill first
    sort_by_supplier_gstin(rows) {
        const text = (row, field) => String(row[field] || "");

        return rows.sort(
            (a, b) =>
                text(a, "supplier_gstin").localeCompare(text(b, "supplier_gstin")) ||
                text(a, "bill_date").localeCompare(text(b, "bill_date")) ||
                text(a, "bill_no").localeCompare(text(b, "bill_no")),
        );
    }

    get_match_status_link(match_status) {
        const info = MATCH_STATUS_INFO[match_status] || "";
        return `<a href="#" class="match-status" title="${frappe.utils.escape_html(
            info,
        )}">${match_status}</a>`;
    }

    get_supplier_name_gstin(row) {
        const status = get_gstin_status_at_invoice_date(row);
        const gstin_link = $(
            `<a href="#" style="font-size: 0.9em;" class="supplier-gstin">${row.supplier_gstin || ""}</a>`,
        )
            .addClass(`indicator ${get_gstin_indicator_color(status)}`)
            .attr("title", status || __("Unknown"))
            .prop("outerHTML");
        return `${row.supplier_name}<br />${gstin_link}`;
    }

    get_value_with_indicator(value, column, data) {
        if (!value) return "";

        let color = "green";
        let title = "Supplier Return: Filed";

        if (!data.is_supplier_return_filed) {
            color = "red";
            title = "Supplier Return: Not Filed";
        }

        value = $(value).addClass(`indicator ${color}`).attr("title", title).prop("outerHTML");

        return value;
    }

    get_accounting_dimensions() {
        let options = ["cost_center", "project"];
        frappe.db.get_list("Accounting Dimension", { fields: ["fieldname"] }).then((res) => {
            res.forEach((dimension) => {
                options.push(dimension.document_type);
            });
        });
        return options;
    }
};

reconciliation.detail_view_dialog = class DetailViewDialog {
    table_fields = [
        "name",
        "bill_no",
        "bill_date",
        "taxable_value",
        "cgst",
        "sgst",
        "igst",
        "cess",
        "is_reverse_charge",
        "place_of_supply",
    ];

    constructor(frm, row) {
        this.frm = frm;
        this.row = row;
        this.render_dialog();
    }

    async render_dialog() {
        await this.get_invoice_details();
        this.process_data();
        this.init_dialog();
        this.setup_actions();
        this.render_html();
        this.dialog.show();
    }

    async get_invoice_details() {
        const { message } = await this.frm._call("get_invoice_details", {
            purchase_name: this.row.purchase_invoice_name,
            inward_supply_name: this.row.inward_supply_name,
        });

        this.data = message;
    }

    process_data() {
        for (let key of ["_purchase_invoice", "_inward_supply"]) {
            const doc = this.data[key];
            if (!doc) continue;

            this.table_fields.forEach((field) => {
                if (field == "is_reverse_charge" && doc[field] != undefined)
                    doc[field] = doc[field] ? "Yes" : "No";
            });
        }
    }

    init_dialog() {
        const supplier_details = `
            <h5 class="mb-1">${frappe.utils.escape_html(this.row.supplier_name || "")}</h5>
            ${this._get_gstin_html()}`;

        this.dialog = new frappe.ui.Dialog({
            title: `Detail View (${this.row.classification})`,
            fields: [
                ...this._get_document_link_fields(),
                {
                    fieldtype: "HTML",
                    fieldname: "supplier_details",
                    options: supplier_details,
                },
                {
                    fieldtype: "HTML",
                    fieldname: "diff_cards",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "detail_table",
                },
            ],
        });

        this.set_link_options();
    }

    // GSTIN and its status, under the supplier name. Imports have no GSTIN: the row
    // falls back to the supplier name there, which the name above already says
    _get_gstin_html() {
        const gstin = this.row.supplier_gstin;
        if (!gstin || gstin === this.row.supplier_name) return "";

        const status = get_gstin_status_at_invoice_date(this.row);
        let note = "";

        if (status === "Active" && this.row.gstin_status === "Cancelled" && this.row.gstin_cancelled_date) {
            note = __("Currently Cancelled since {0}", [
                frappe.datetime.str_to_user(this.row.gstin_cancelled_date),
            ]);
        } else if (status === "Cancelled" && this.row.gstin_cancelled_date) {
            note = __("Cancelled since {0}", [frappe.datetime.str_to_user(this.row.gstin_cancelled_date)]);
        }

        return `
            <div class="d-flex align-items-center flex-wrap">
                <span class="text-muted mr-2">${frappe.utils.escape_html(gstin)}</span>
                <span class="es-badge" data-size="sm" data-theme="${get_gstin_indicator_color(
                    status,
                )}" title="${__("GSTIN Status")}">${status || __("Unknown")}</span>
                ${note ? `<span class="text-muted ml-2">${note}</span>` : ""}
            </div>`;
    }

    _get_document_link_fields() {
        this._set_missing_doctype();
        if (!this.missing_doctype) return [];

        // everything that narrows the search, then the document those filters turned up
        return [
            {
                fieldtype: "Section Break",
                fieldname: "filters_section",
                label: __("Link Filters"),
                collapsible: 1,
                collapsible_depends_on: "eval:!doc.link_with",
                css_class: "link-filters",
            },
            {
                label: "Document Type",
                fieldtype: "Autocomplete",
                fieldname: "doctype",
                default: this.missing_doctype,
                options: this.doctype_options,
                read_only_depends_on: this.doctype_options.length === 1,
                onchange: () => this.set_link_options(),
            },
            {
                label: "Date Range",
                fieldtype: "DateRange",
                fieldname: "date_range",
                onchange: () => this.set_link_options(),
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: "GSTIN",
                fieldtype: "Data",
                fieldname: "supplier_gstin",
                default: this.row.supplier_gstin,
                onchange: () => this.set_link_options(),
            },
            {
                label: __("Show matched documents"),
                fieldtype: "Check",
                fieldname: "show_matched",
                onchange: () => this.set_link_options(),
            },
            {
                fieldtype: "Section Break",
                hide_border: 1,
            },
            {
                label: `Document Name`,
                fieldtype: "Autocomplete",
                fieldname: "link_with",
                onchange: () => this.refresh_data(),
            },
            {
                fieldtype: "Section Break",
            },
        ];
    }

    async set_link_options(method) {
        if (!this.dialog.get_value("doctype")) return;

        // left blank on purpose, the server falls back to its own window
        const date_range = this.dialog.get_value("date_range") || [];

        this.filters = {
            supplier_gstin: this.dialog.get_value("supplier_gstin"),
            from_date: date_range[0],
            to_date: date_range[1],
            show_matched: this.dialog.get_value("show_matched"),
            purchase_doctype: this.data.purchase_doctype,
        };

        const { message } = await this.frm._call("get_link_options", {
            doctype: this.dialog.get_value("doctype"),
            filters: this.filters,
        });

        const { options, filters } = message;
        const field = this.dialog.get_field("link_with");
        field.set_data(options);
        field.set_description(this._get_filter_note(filters, options.length));
    }

    // says what the server filtered on, including dates it filled in for a blank range
    _get_filter_note({ from_date, to_date, show_matched }, count) {
        const scope = show_matched ? __("All") : __("Unmatched");
        const dates = [from_date, to_date].filter(Boolean).map((d) => frappe.datetime.str_to_user(d));
        const note = dates.length == 2 ? __("{0} between {1} to {2}", [scope, ...dates]) : scope;

        return count ? note : `${__("No documents found.")} ${note}`;
    }

    _set_missing_doctype() {}

    setup_actions() {
        const actions = this._get_custom_actions();

        actions.forEach((action) => {
            this.dialog.add_custom_action(
                action,
                () => {
                    this._apply_custom_action(action);
                    this.dialog.hide();
                },
                `mr-2 ${this._get_button_css(action)}`,
            );
        });

        this.dialog.$wrapper.find(".btn.btn-secondary.not-grey").removeClass("btn-secondary");
        this.dialog.$wrapper.find(".modal-footer").css("flex-direction", "inherit");
    }

    _get_custom_actions() {
        return [];
    }

    _apply_custom_action(action) {}

    _get_button_css(action) {
        return "btn-secondary";
    }

    toggle_link_btn(disabled) {
        const btn = this.dialog.$wrapper.find(".modal-footer .link-document-btn");
        if (disabled) btn.addClass("disabled");
        else btn.removeClass("disabled");
    }

    async refresh_data() {
        this.toggle_link_btn(true);
        const field = this.dialog.get_field("link_with");
        if (field.value) this.toggle_link_btn(false);

        if (this.missing_doctype == "GST Inward Supply") this.row.inward_supply_name = field.value;
        else this.row.purchase_invoice_name = field.value;

        await this.get_invoice_details();
        this.process_data();

        this.row = this.data;
        this.render_html();
    }

    render_html() {
        this.render_cards();
        this.render_table();
    }

    render_cards() {
        let cards = [
            {
                value: this.row.tax_difference,
                label: "Tax Difference",
                datatype: "Currency",
                currency: frappe.boot.sysdefaults.currency,
                indicator: this.row.tax_difference === 0 ? "text-success" : "text-danger",
            },
            {
                value: this.row.taxable_value_difference,
                label: "Taxable Amount Difference",
                datatype: "Currency",
                currency: frappe.boot.sysdefaults.currency,
                indicator: this.row.taxable_value_difference === 0 ? "text-success" : "text-danger",
            },
        ];

        if (!this.row.purchase_invoice_name || !this.row.inward_supply_name) cards = [];

        new india_compliance.NumberCardManager({
            $wrapper: this.dialog.fields_dict.diff_cards.$wrapper,
            cards: cards,
        });
    }

    render_table() {
        const detail_table = this.dialog.fields_dict.detail_table;

        detail_table.html(
            frappe.render_template("invoice_detail_comparison", {
                purchase: this.data._purchase_invoice,
                inward_supply: this.data._inward_supply,
                // nothing booked yet: name the column after the document waiting to be linked
                purchase_label: this.data._purchase_invoice.doctype || this.missing_doctype || __("Books"),
            }),
        );
        this._mark_differences(detail_table.$wrapper);
    }

    _mark_differences(wrapper) {
        // one side missing: nothing to compare against, and nothing to copy over
        if (!this.row.purchase_invoice_name || !this.row.inward_supply_name) return;

        const can_sync = frappe.model.can_write(this.row.purchase_doctype);

        // template marks the rows worth comparing
        wrapper.find("[data-compare]").each((_index, row) => {
            const field = $(row).data("compare");
            const booked = this.data._purchase_invoice[field];
            const reported = this.data._inward_supply[field];

            const same =
                typeof booked === "number" || typeof reported === "number"
                    ? flt(booked, 2) === flt(reported, 2)
                    : booked == reported;

            if (same) return;

            $(row).attr("title", __("Books and 2A/2B do not match")).addClass("not-matched");

            // nothing to copy from a blank 2A/2B value, leave the button hidden
            if (!can_sync || !reported) return;

            $(row)
                .find("[data-field]")
                .addClass("sync-detail")
                .on("click", () => this._sync_field(field));
        });
    }

    async _sync_field(field) {
        await reconciliation.sync_details(this.frm, [this.row], [field]);

        await this.get_invoice_details();
        this.process_data();
        this.render_html();
    }
};
