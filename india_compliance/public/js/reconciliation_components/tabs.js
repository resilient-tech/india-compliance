frappe.provide("reconciliation");

reconciliation.reconciliation_tabs = class ReconciliationTabs {
    constructor(frm, tabs, data_field) {
        this.frm = frm;
        this.data = [];
        this._tabs = tabs;
        this.$wrapper = frm.get_field(data_field).$wrapper;

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

        this._tabs.forEach(tab => {
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
        this.tabs = Object.fromEntries(
            this.tab_group.tabs.map(tab => [tab.df.fieldname, tab])
        );
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

        dimension_fields.forEach(dimension => {
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
        this.filtered_data = this.data.filter(row => {
            return filters.every(filter =>
                india_compliance.FILTER_OPERATORS[filter[2]](
                    filter[3] || "",
                    row[filter[1]] || ""
                )
            );
        });
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

    render_data_tables() {
        this._tabs.forEach(tab => {
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

    get_supplier_name_gstin(row) {
        return `
        ${row.supplier_name}
        <br />
        <a href="#" style="font-size: 0.9em;" class="supplier-gstin">
            ${row.supplier_gstin || ""}
        </a>
        `;
    }

    get_value_with_indicator(value, column, data) {
        if (!value) return "";

        let color = "green";
        let title = "Supplier Return: Filed";

        if (!data.is_supplier_return_filed) {
            color = "red";
            title = "Supplier Return: Not Filed";
        }

        value = $(value)
            .addClass(`indicator ${color}`)
            .attr("title", title)
            .prop("outerHTML");

        return value;
    }

    get_accounting_dimensions() {
        let options = ["cost_center", "project"];
        frappe.db
            .get_list("Accounting Dimension", { fields: ["fieldname"] })
            .then(res => {
                res.forEach(dimension => {
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

            this.table_fields.forEach(field => {
                if (field == "is_reverse_charge" && doc[field] != undefined)
                    doc[field] = doc[field] ? "Yes" : "No";
            });
        }
    }

    init_dialog() {
        const supplier_details = `
        <h5>${this.row.supplier_name}
        ${this.row.supplier_gstin ? ` (${this.row.supplier_gstin})` : ""}
        </h5>
        `;

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

    _get_document_link_fields() {
        this._set_missing_doctype();
        if (!this.missing_doctype) return [];

        return [
            {
                label: "GSTIN",
                fieldtype: "Data",
                fieldname: "supplier_gstin",
                default: this.row.supplier_gstin,
                onchange: () => this.set_link_options(),
            },
            {
                label: "Date Range",
                fieldtype: "DateRange",
                fieldname: "date_range",
                default: this._get_default_date_range(),
                onchange: () => this.set_link_options(),
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: "Document Type",
                fieldtype: "Autocomplete",
                fieldname: "doctype",
                default: this.missing_doctype,
                options: this.doctype_options,
                read_only_depends_on: this.doctype_options.length === 1,

                onchange: () => {
                    const doctype = this.dialog.get_value("doctype");
                    this.dialog
                        .get_field("show_matched")
                        .set_label(`Show matched options for linking ${doctype}`);
                },
            },
            {
                label: `Document Name`,
                fieldtype: "Autocomplete",
                fieldname: "link_with",
                onchange: () => this.refresh_data(),
            },
            {
                label: `Show matched options for linking ${this.missing_doctype}`,
                fieldtype: "Check",
                fieldname: "show_matched",
                onchange: () => this.set_link_options(),
            },
            {
                fieldtype: "Section Break",
            },
        ];
    }

    async set_link_options(method) {
        if (!this.dialog.get_value("doctype")) return;

        this.filters = {
            supplier_gstin: this.dialog.get_value("supplier_gstin"),
            bill_from_date: this.dialog.get_value("date_range")[0],
            bill_to_date: this.dialog.get_value("date_range")[1],
            show_matched: this.dialog.get_value("show_matched"),
            purchase_doctype: this.data.purchase_doctype,
        };

        const { message } = await this.frm._call("get_link_options", {
            doctype: this.dialog.get_value("doctype"),
            filters: this.filters,
        });

        this.dialog.get_field("link_with").set_data(message);
    }

    _set_missing_doctype() {}

    _get_default_date_range() {
        const now = frappe.datetime.now_date();
        return [frappe.datetime.add_months(now, -12), now];
    }

    setup_actions() {
        const actions = this._get_custom_actions();

        actions.forEach(action => {
            this.dialog.add_custom_action(
                action,
                () => {
                    this._apply_custom_action(action);
                    this.dialog.hide();
                },
                `mr-2 ${this._get_button_css(action)}`
            );
        });

        this.dialog.$wrapper
            .find(".btn.btn-secondary.not-grey")
            .removeClass("btn-secondary");
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
        const btn = this.dialog.$wrapper.find(".modal-footer .btn-link");
        if (disabled) btn.addClass("disabled");
        else btn.removeClass("disabled");
    }

    async refresh_data() {
        this.toggle_link_btn(true);
        const field = this.dialog.get_field("link_with");
        if (field.value) this.toggle_link_btn(false);

        if (this.missing_doctype == "GST Inward Supply")
            this.row.inward_supply_name = field.value;
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
                indicator:
                    this.row.tax_difference === 0 ? "text-success" : "text-danger",
            },
            {
                value: this.row.taxable_value_difference,
                label: "Taxable Amount Difference",
                datatype: "Currency",
                currency: frappe.boot.sysdefaults.currency,
                indicator:
                    this.row.taxable_value_difference === 0
                        ? "text-success"
                        : "text-danger",
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
            })
        );
        detail_table.$wrapper.removeClass("not-matched");
        this._set_value_color(detail_table.$wrapper);
    }

    _set_value_color(wrapper) {
        if (!this.row.purchase_invoice_name || !this.row.inward_supply_name) return;

        ["place_of_supply", "is_reverse_charge"].forEach(field => {
            if (this.data._purchase_invoice[field] == this.data._inward_supply[field])
                return;

            wrapper
                .find(`[data-label='${field}'], [data-label='${field}']`)
                .addClass("not-matched");
        });
    }
};
