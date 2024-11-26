// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

const api_enabled = india_compliance.is_api_enabled();

frappe.ui.form.on("GST Invoice Management System", {
    async setup(frm) {
        await frappe.require("ims.bundle.js");
        frm.ims = new IMS(frm);

        frm.trigger("company");
    },

    async company(frm) {
        render_empty_state(frm);
        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);

        if (!frm.doc.company_gstin) frm.set_value("company_gstin", options[0]);
    },

    company_gstin(frm) {
        render_empty_state(frm);
    },

    refresh(frm) {
        // Primary Action
        frm.disable_save();
        if (!frm.doc.is_data_loaded) {
            frm.page.clear_primary_action();

            frm.page.set_primary_action(__("Generate"), async () => {
                const { message } = await frm.call("get_invoice_data");
                frm.doc.__invoice_data = message;

                // Toggle HTML fields
                frm.refresh();

                frm.ims.generate_data();
                frm.doc.is_data_loaded = true;
            });
        } else {
            frm.page.clear_primary_action();

            frm.page.set_primary_action(__("Upload Invoices"), async () => {
                frappe.show_alert(__("Uploading Invoices"));

                await taxpayer_api.call({
                    method: "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.upload_invoices",
                    args: {
                        company_gstin: frm.doc.company_gstin,
                    },
                    callback: () => frm.ims.check_action_status_with_retry(),
                });

                frappe.show_alert({
                    message: "Uploaded Invoices",
                    indicator: "green",
                });
            });

            frm.add_custom_button(
                __("Accept"),
                () => {
                    apply_bulk_action(frm, "Accept");
                },
                __("Actions")
            );
            frm.add_custom_button(
                __("Reject"),
                () => {
                    apply_bulk_action(frm, "Reject");
                },
                __("Actions")
            );
            frm.add_custom_button(
                __("Pending"),
                () => {
                    apply_bulk_action(frm, "Pending");
                },
                __("Actions")
            );
            frm.add_custom_button(
                __("No Action"),
                () => {
                    apply_bulk_action(frm, "No Action");
                },
                __("Actions")
            );

            // move actions button next to filters
            for (let button of $(".custom-actions .inner-group-button")) {
                if (button.innerText?.trim() != "Actions") continue;
                $(".custom-button-group .inner-group-button").remove();
                $(button).appendTo($(".custom-button-group"));
            }
        }

        frm.add_custom_button(__("Download Invoices"), async () => {
            await taxpayer_api.call({
                method: "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.download_invoices_and_reconcile",
                args: {
                    company_gstin: frm.doc.company_gstin,
                    company: frm.doc.company,
                },
            });

            frappe.show_alert({
                message: "Downloaded and Reconciled Invoices.",
                indicator: "green",
            });
        });
    },
});

class IMS {
    RETRY_INTERVALS = [2000, 3000, 15000, 30000, 60000, 120000, 300000, 600000, 720000]; // 5 second, 15 second, 30 second, 1 min, 2 min, 5 min, 10 min, 12 min

    constructor(frm) {
        this.init(frm);
        this.render_tab_group();
        this.setup_filter_button();
    }

    init(frm) {
        this.frm = frm;
        this.data = [];
        this.frm.doc.is_data_loaded = false;
        this.$wrapper = this.frm.get_field("invoice_html").$wrapper;
        this._tabs = ["invoice", "summary"];
    }

    generate_data() {
        this.data = this.frm.doc.__invoice_data;
        this.filtered_data = this.frm.doc.__invoice_data;

        // clear filters
        this.filter_group.filter_x_button.click();
        this.render_data_tables();
    }

    refresh(data) {
        if (data) {
            this.data = data;
            this.refresh_filter_fields();
        }

        this.apply_filters();

        // data unchanged!
        if (this.rendered_data == this.filtered_data) return;

        this._tabs.forEach(tab => {
            this.tabs[`${tab}_tab`].refresh(this[`get_${tab}_data`]());
        });

        this.rendered_data = this.filtered_data;
    }

    refresh_filter_fields() {
        this.filter_group.filter_options.filter_fields = this.get_filter_fields();
    }

    render_tab_group() {
        this.tab_group = new frappe.ui.FieldGroup({
            fields: [
                {
                    //hack: for the FieldGroup(Layout) to avoid rendering default "details" tab
                    fieldtype: "Section Break",
                },
                {
                    label: "Match Summary",
                    fieldtype: "Tab Break",
                    fieldname: "summary_tab",
                    active: 1,
                },
                {
                    fieldtype: "HTML",
                    fieldname: "summary_data",
                },
                {
                    label: "Document View",
                    fieldtype: "Tab Break",
                    fieldname: "invoice_tab",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "invoice_data",
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

    setup_filter_button() {
        this.filter_group = new india_compliance.FilterGroup({
            doctype: "GST Invoice Management System",
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
        const fields = [
            {
                label: "Supplier Name",
                fieldname: "supplier_name",
                fieldtype: "Autocomplete",
                options: this.get_autocomplete_options("supplier_name"),
            },
            {
                label: "Supplier GSTIN",
                fieldname: "supplier_gstin",
                fieldtype: "Autocomplete",
                options: this.get_autocomplete_options("supplier_gstin"),
            },
            {
                label: "Match Status",
                fieldname: "match_status",
                fieldtype: "Select",
                options: [
                    "Exact Match",
                    "Suggested Match",
                    "Mismatch",
                    "Manual Match",
                    "Missing in PI",
                ],
            },
            {
                label: "Action",
                fieldname: "ims_action",
                fieldtype: "Select",
                options: ["Accept", "Reject", "Pending", "No Action"],
            },
        ];

        fields.forEach(field => (field.parent = "GST Invoice Management System"));
        return fields;
    }

    apply_filters() {
        const has_filters = this.filter_group.filters.length > 0;
        if (!has_filters) {
            this.filters = null;
            this.filtered_data = this.data;
            return;
        }

        let filters = this.filter_group.get_filters();
        if (this.filters === filters) return;

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

    render_data_tables() {
        this._tabs.forEach(tab => {
            this.tabs[`${tab}_tab`] = new india_compliance.DataTableManager({
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

    set_listeners() {
        const me = this;

        this.tabs.invoice_tab.$datatable.on("click", ".supplier-gstin", function (e) {
            add_filter(e, "supplier_gstin", $(this).text().trim(), me);
        });

        this.tabs.invoice_tab.$datatable.on("click", ".match-status", function (e) {
            add_filter(e, "match_status", $(this).text(), me);
        });

        this.tabs.summary_tab.$datatable.on("click", ".match-status", function (e) {
            add_filter(e, "match_status", $(this).text(), me);
        });

        this.tabs.invoice_tab.$datatable.on("click", ".ims-action", function (e) {
            add_filter(e, "ims_action", $(this).text(), me);
        });

        this.tabs.invoice_tab.$datatable.on("click", ".btn.eye", function (e) {
            const row = me.mapped_invoice_data[$(this).attr("data-name")];
            me.dm = new DetailViewDialog(me.frm, row);
        });

        async function add_filter(e, field, field_value, me) {
            e.preventDefault();

            await me.filter_group.push_new_filter([
                "GST Invoice Management System",
                field,
                "=",
                field_value,
            ]);
            me.filter_group.apply();
        }
    }

    get_summary_columns() {
        return [
            {
                label: "Match Status",
                fieldname: "match_status",
                width: 200,
                _value: (...args) => `<a href="#" class='match-status'>${args[0]}</a>`,
            },
            {
                label: "Count <br>2A/2B Docs",
                fieldname: "inward_supply_count",
                width: 120,
                align: "center",
            },
            {
                label: "Count <br>Purchase Docs",
                fieldname: "purchase_count",
                width: 120,
                align: "center",
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_difference",
                width: 180,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_difference",
                width: 180,
                align: "center",
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "% Action Taken",
                fieldname: "action_taken",
                width: 120,
                align: "center",
                _value: (...args) => {
                    return (
                        roundNumber(
                            (args[2].action_taken_count / args[2].total_docs) * 100,
                            2
                        ) + " %"
                    );
                },
            },
        ];
    }

    get_summary_data() {
        if (!this.data.length) return [];

        const data = {};
        this.filtered_data.forEach(row => {
            let new_row = data[row.match_status];
            if (!new_row) {
                new_row = data[row.match_status] = {
                    match_status: row.match_status,
                    inward_supply_count: 0,
                    purchase_count: 0,
                    action_taken_count: 0,
                    total_docs: 0,
                    tax_difference: 0,
                    taxable_value_difference: 0,
                };
            }
            if (row.inward_supply_name) new_row.inward_supply_count += 1;
            if (row.purchase_invoice_name) new_row.purchase_count += 1;
            if (row.ims_action != "No Action") new_row.action_taken_count += 1;
            new_row.total_docs += 1;
            new_row.tax_difference += row.tax_difference || 0;
            new_row.taxable_value_difference += row.taxable_value_difference || 0;
        });

        return Object.values(data);
    }

    get_invoice_data() {
        if (!this.data.length) return [];

        const data = [];
        this.mapped_invoice_data = {};

        this.filtered_data.forEach(row => {
            this.mapped_invoice_data[row.inward_supply_name] = row;

            data.push({
                supplier_name_gstin: this.get_supplier_name_gstin(row),
                invoice_no: row.bill_no,
                invoice_type: row._inward_supply.supply_type,
                ims_action: row.ims_action || "",
                match_status: row.match_status,
                linked_doc: row.purchase_invoice_name,
                tax_difference: row.tax_difference,
                taxable_value_difference: row.taxable_value_difference,
                inward_supply_name: row.inward_supply_name,
            });
        });

        return data;
    }

    get_invoice_columns() {
        return [
            {
                fieldname: "view",
                fieldtype: "html",
                width: 60,
                align: "center",
                _value: (...args) => get_icon(...args),
            },
            {
                label: "Supplier Name",
                fieldname: "supplier_name_gstin",
                align: "center",
                width: 220,
            },
            {
                label: "Invoice No.",
                fieldname: "invoice_no",
                align: "center",
                width: 180,
            },
            {
                label: "Invoice Type",
                fieldname: "invoice_type",
                align: "center",
                width: 80,
            },
            {
                label: "Action",
                fieldname: "ims_action",
                align: "center",
                width: 100,
                _value: (...args) => `<a href="#" class='ims-action'>${args[0]}</a>`,
            },
            {
                label: "Match Status",
                fieldname: "match_status",
                align: "center",
                width: 100,
                _value: (...args) => `<a href="#" class='match-status'>${args[0]}</a>`,
            },
            {
                label: "Linked Voucher",
                fieldname: "linked_doc",
                align: "center",
                width: 150,
                fieldtype: "Dynamic Link",
                options: "linked_voucher_type",
            },
            {
                label: "Tax Difference",
                fieldname: "tax_difference",
                align: "center",
                width: 150,
            },
            {
                label: "Taxable Value Difference",
                fieldname: "taxable_value_difference",
                align: "center",
                width: 150,
            },
        ];
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

    get_autocomplete_options(field) {
        const options = [];
        this.data.forEach(row => {
            if (row[field] && !options.includes(row[field])) options.push(row[field]);
        });
        return options;
    }

    check_action_status_with_retry(retries = 0, now = false) {
        setTimeout(
            async () => {
                const { message } = await taxpayer_api.call({
                    method: `india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.check_action_status`,
                    args: {
                        company_gstin: this.frm.doc.company_gstin,
                    },
                });

                if (!message.status_cd) return;

                if (
                    message.status_cd === "IP" &&
                    retries < this.RETRY_INTERVALS.length
                ) {
                    return this.check_action_status_with_retry(retries + 1);
                }

                // Not IP

                if (message.status_cd == "P") {
                    // TODO: Do Something
                } else if (message.status_cd == "PE") {
                    // TODO: Show error report
                }

                if (message.status_cd == "ER") frappe.throw(__(message.error.message));
            },
            now ? 0 : this.RETRY_INTERVALS[retries]
        );
    }
}

class DetailViewDialog {
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
        const { message } = await frappe.call({
            method: "get_invoice_comparision",
            doc: this.frm,
            args: {
                purchase_name: this.row.purchase_invoice_name,
                inward_supply_name: this.row.inward_supply_name,
            },
        });

        this.comparision_data = message;
    }

    process_data() {
        for (let key of ["_purchase_invoice", "_inward_supply"]) {
            const doc = this.comparision_data[key];
            if (!doc) continue;

            this.table_fields.forEach(field => {
                if (field == "is_reverse_charge" && doc[field] != undefined)
                    doc[field] = doc[field] ? "Yes" : "No";
            });
        }
    }

    init_dialog() {
        const supplier_details = `
        <h5>${this.comparision_data.supplier_name}
        ${
            this.comparision_data.supplier_gstin
                ? ` (${this.comparision_data.supplier_gstin})`
                : ""
        }
        </h5>
        `;

        this.dialog = new frappe.ui.Dialog({
            title: `Detail View (${this.comparision_data.classification})`,
            fields: [
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
    }

    render_html() {
        this.render_cards();
        this.render_table();
    }

    render_cards() {
        let cards = [
            {
                value: this.comparision_data.tax_difference,
                label: "Tax Difference",
                datatype: "Currency",
                currency: frappe.boot.sysdefaults.currency,
                indicator:
                    this.comparision_data.tax_difference === 0
                        ? "text-success"
                        : "text-danger",
            },
            {
                value: this.comparision_data.taxable_value_difference,
                label: "Taxable Amount Difference",
                datatype: "Currency",
                currency: frappe.boot.sysdefaults.currency,
                indicator:
                    this.comparision_data.taxable_value_difference === 0
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
            frappe.render_template("invoice_detail_comparision", {
                purchase: this.comparision_data._purchase_invoice,
                inward_supply: this.comparision_data._inward_supply,
            })
        );
    }

    setup_actions() {
        // setup actions
        ["Accept", "Reject", "Pending", "No Action"].forEach(action => {
            this.dialog.add_custom_action(
                action,
                () => {
                    apply_action(this.frm, [this.row.inward_supply_name], action);
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

    _get_button_css(action) {
        if (action == "Accept") return "btn-success not-grey";
        if (action == "Reject") return "btn-danger not-grey";
        if (action == "Pending") return "btn-warning not-grey";
        if (action == "No Action") return "btn-secondary";
    }
}

function render_empty_state(frm) {
    frm.doc.__invoice_data = null;
    frm.doc.is_data_loaded = false;

    frm.refresh();
}
function apply_bulk_action(frm, action) {
    const active_tab = frm.get_active_tab()?.df.fieldname;
    if (!active_tab) return;

    const tab = frm.ims.tabs[active_tab];
    affected_invoices = tab.get_checked_items();

    const selected_rows = tab.get_checked_items();
    const invoice_names = get_affected_rows(
        active_tab,
        selected_rows,
        frm.ims.filtered_data
    );

    if (!affected_invoices.length)
        return frappe.show_alert({
            message: __("Please select invoices"),
            indicator: "red",
        });

    apply_action(frm, invoice_names, action);

    if (tab) tab.clear_checked_items();
}

async function apply_action(frm, invoice_names, action) {
    // Update action in UI
    let pending_not_allowed = [];
    const new_data = frm.ims.data.filter(row => {
        if (!invoice_names.includes(row.inward_supply_name)) return true;

        if (!validate_pending_action(row, action)) {
            pending_not_allowed.push(row.inward_supply_name);
            return true;
        }

        row.ims_action = action;

        return true;
    });

    invoice_names = invoice_names.filter(name => !pending_not_allowed.includes(name));

    frm.ims.refresh(new_data);

    if (pending_not_allowed.length) {
        frappe.msgprint(
            `The following invoices are not allowed to be marked as Pending: ${pending_not_allowed.join(
                ", "
            )}`
        );
    }

    if (!invoice_names.length) return;

    // Update action in database
    await frappe.call({
        method: "update_action",
        doc: frm,
        args: { invoice_names, action },
    });

    frappe.show_alert({
        message: "Action applied successfully",
        indicator: "green",
    });
}

function validate_pending_action(row, action) {
    if (action === "Pending" && !row.is_pending_action_allowed) return false;
    return true;
}

function get_icon(value, column, data) {
    return `<button class="btn eye" data-name="${data.inward_supply_name}">
                <i class="fa fa-eye"></i>
            </button>`;
}

function get_affected_rows(tab, selection, data) {
    let invoices = [];
    if (tab == "invoice_tab") invoices = selection;

    if (tab == "summary_tab")
        invoices = data.filter(
            inv => selection.filter(row => row.match_status == inv.match_status).length
        );

    return invoices.map(row => row.inward_supply_name);
}
