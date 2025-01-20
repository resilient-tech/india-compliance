frappe.provide("india_compliance");

india_compliance.summary_view = class SummaryView {
    constructor(frm, doctype) {
        this.init(frm);
        this.render_tab_group();
        this.setup_filter_button(doctype);
    }

    init(frm, tabs) {
        this.frm = frm;
        this.data = [];
        this._tabs = tabs;
    }

    generate_data(data_key) {
        this.data = this.frm[data_key];
        this.filtered_data = this.frm[data_key];

        // clear filters
        this.filter_group.filter_x_button.click();
        this.render_data_tables();
    }

    refresh(data) {
        if (data) {
            this.data = data;
            this.refresh_filter_fields();
        }

        this.apply_filters(!!data); // TODO: Is this required in IMS ??

        // data unchanged!
        if (this.rendered_data == this.filtered_data) return;

        this._tabs.forEach(tab => {
            this.tabs[`${tab}_tab`].datatable?.refresh(this[`get_${tab}_data`]());
        });

        this.rendered_data = this.filtered_data;
    }

    render_tab_group(fields) {
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

    get_filter_fields() {}

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
};

india_compliance.detail_view_dialog = class DetailViewDialog {
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

    async get_invoice_details() {}

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

    _get_document_link_fields() {}

    async set_link_options(method, args = {}) {
        if (!this.dialog.get_value("doctype")) return;

        this.filters = {
            supplier_gstin: this.dialog.get_value("supplier_gstin"),
            bill_from_date: this.dialog.get_value("date_range")[0],
            bill_to_date: this.dialog.get_value("date_range")[1],
            show_matched: this.dialog.get_value("show_matched"),
            purchase_doctype: this.data.purchase_doctype,
        };

        args["filters"] = this.filters;

        const { message } = await this.frm._call(method, args);

        this.dialog.get_field("link_with").set_data(message);
    }

    setup_actions(actions) {
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

    _apply_custom_action(_class, action, doc_name, apply_action_method) {
        if (action == "Unlink") {
            reconciliation.unlink_documents(this.frm, _class, [this.row]);
        } else if (action == "Link") {
            reconciliation.link_documents(
                this.frm,
                this.data.purchase_invoice_name,
                this.data.inward_supply_name,
                this.dialog.get_value("doctype"),
                _class,
                true
            );
        } else if (action == "Create") {
            reconciliation.create_new_purchase_invoice(
                this.data,
                this.frm.doc.company,
                this.frm.doc.company_gstin,
                DOCTYPE
            );
        } else {
            apply_action_method(this.frm, action, [doc_name]);
        }
    }

    _get_button_css(action) {}

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

    render_table(template) {
        const detail_table = this.dialog.fields_dict.detail_table;

        detail_table.html(
            frappe.render_template(template, {
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
