// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("purchase_reconciliation_tool");

const tooltip_info = {
    purchase_period: "Returns purchases during this period where no match is found.",
    inward_supply_period:
        "Returns all documents from GSTR 2A/2B during this return period.",
};

const api_enabled = india_compliance.is_api_enabled();
const ALERT_HTML = `
    <div class="gstr2b-alert alert alert-primary fade show d-flex align-items-center justify-content-between border-0" role="alert">
        <div>
            You have missing GSTR-2B downloads
        </div>
        ${
            api_enabled
                ? `<button
                id="download-gstr2b-button"
                type="button"
                class="btn btn-dark btn-xs"
                aria-label="Download"
                style="outline: 0px solid black !important"
            >
                Download 2B
            </button>`
                : ""
        }
    </div>
`;

const ReturnType = {
    GSTR2A: "GSTR2a",
    GSTR2B: "GSTR2b",
};

function remove_gstr2b_alert(alert) {
    if (alert.length === 0) return;
    $(alert).remove();
}

async function add_gstr2b_alert(frm) {
    let existing_alert = frm.layout.wrapper.find(".gstr2b-alert");

    if (!frm.doc.inward_supply_period || !frm.doc.__onload?.has_missing_2b_documents) {
        remove_gstr2b_alert(existing_alert);
        return;
    }

    // Add alert only if there is no existing alert
    if (existing_alert.length !== 0) return;

    existing_alert = $(ALERT_HTML).prependTo(frm.layout.wrapper);
    $(existing_alert)
        .find("#download-gstr2b-button")
        .on("click", async function () {
            await download_gstr(
                frm,
                [frm.doc.inward_supply_from_date, frm.doc.inward_supply_to_date],
                ReturnType.GSTR2B,
                true
            );
            remove_gstr2b_alert(existing_alert);
        });
}

frappe.ui.form.on("Purchase Reconciliation Tool", {
    async setup(frm) {
        patch_set_active_tab(frm);
        new india_compliance.quick_info_popover(frm, tooltip_info);

        await frappe.require("purchase_reconciliation_tool.bundle.js");
        frm.purchase_reconciliation_tool = new PurchaseReconciliationTool(frm);
    },

    onload(frm) {
        if (frm.doc.is_modified) frm.doc.reconciliation_data = null;
        frm.trigger("company");
        add_gstr2b_alert(frm);
    },

    async company(frm) {
        if (!frm.doc.company) return;
        const options = await set_gstin_options(frm);

        if (!frm.doc.company_gstin) frm.set_value("company_gstin", options[0]);
    },

    refresh(frm) {
        // Primary Action
        frm.disable_save();
        frm.page.set_primary_action(__("Reconcile"), () => frm.save());

        // add custom buttons
        api_enabled
            ? frm.add_custom_button(__("Download 2A/2B"), () => new ImportDialog(frm))
            : frm.add_custom_button(
                  __("Upload 2A/2B"),
                  () => new ImportDialog(frm, false)
              );

        if (!frm.purchase_reconciliation_tool?.data?.length) return;
        if (frm.get_active_tab()?.df.fieldname == "invoice_tab") {
            frm.add_custom_button(
                __("Unlink"),
                () => unlink_documents(frm),
                __("Actions")
            );
            frm.add_custom_button(__("dropdown-divider"), () => {}, __("Actions"));
        }
        ["Accept My Values", "Accept Supplier Values", "Pending", "Ignore"].forEach(
            action =>
                frm.add_custom_button(
                    __(action),
                    () => apply_action(frm, action),
                    __("Actions")
                )
        );
        frm.$wrapper
            .find("[data-label='dropdown-divider']")
            .addClass("dropdown-divider");

        // Export button
        frm.add_custom_button(__("Export"), () =>
            frm.purchase_reconciliation_tool.export_data()
        );

        // move actions button next to filters
        for (let button of $(".custom-actions .inner-group-button")) {
            if (button.innerText?.trim() != "Actions") continue;
            $(".custom-button-group .inner-group-button").remove();
            $(button).appendTo($(".custom-button-group"));
        }
    },

    before_save(frm) {
        frm.doc.__unsaved = true;
        frm.doc.reconciliation_data = null;
    },

    purchase_period(frm) {
        fetch_date_range(frm, "purchase");
    },

    async inward_supply_period(frm) {
        await fetch_date_range(
            frm,
            "inward_supply",
            "get_date_range_and_check_missing_documents"
        );
        add_gstr2b_alert(frm);

    },

    after_save(frm) {
        frm.purchase_reconciliation_tool.refresh(
            frm.doc.reconciliation_data ? JSON.parse(frm.doc.reconciliation_data) : []
        );
    },

    show_progress(frm, type) {
        if (type == "download") {
            frappe.run_serially([
                () => frm.events.update_progress(frm, "update_api_progress"),
                () => frm.events.update_progress(frm, "update_transactions_progress"),
            ]);
        } else if (type == "upload") {
            frm.events.update_progress(frm, "update_transactions_progress");
        }
    },

    update_progress(frm, method) {
        frappe.realtime.on(method, data => {
            const { current_progress } = data;
            const message =
                method == "update_api_progress"
                    ? __("Fetching data from GSTN")
                    : __("Updating Inward Supply for Return Period {0}", [
                          data.return_period,
                      ]);

            frm.dashboard.show_progress(
                "Import GSTR Progress",
                current_progress,
                message
            );
            if (data.is_last_period) {
                frm.flag_last_return_period = data.return_period;
            }
            if (
                current_progress === 100 &&
                method != "update_api_progress" &&
                frm.flag_last_return_period == data.return_period
            ) {
                setTimeout(() => {
                    frm.dashboard.hide();
                    frm.refresh();
                    frm.dashboard.set_headline("Successfully Imported");
                    setTimeout(() => {
                        frm.dashboard.clear_headline();
                    }, 2000);
                    frm.save();
                }, 1000);
            }
        });
    },
});

class PurchaseReconciliationTool {
    constructor(frm) {
        this.init(frm);
        this.render_tab_group();
        this.setup_filter_button();
        this.render_data_tables();
    }

    init(frm) {
        this.frm = frm;
        this.data = frm.doc.reconciliation_data
            ? JSON.parse(frm.doc.reconciliation_data)
            : [];
        this.filtered_data = this.data;
        this.$wrapper = this.frm.get_field("reconciliation_html").$wrapper;
        this._tabs = ["invoice", "supplier", "summary"];
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
            this.tabs[`${tab}_tab`].refresh(this[`get_${tab}_data`]());
        });

        this.rendered_data = this.filtered_data;
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
                    label: "Supplier View",
                    fieldtype: "Tab Break",
                    fieldname: "supplier_tab",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "supplier_data",
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
            doctype: "Purchase Reconciliation Tool",
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
                    "Missing in 2A/2B",
                    "Missing in PI",
                ],
            },
            {
                label: "Action",
                fieldname: "action",
                fieldtype: "Select",
                options: [
                    "No Action",
                    "Accept My Values",
                    "Accept Supplier Values",
                    "Ignore",
                    "Pending",
                ],
            },
            {
                label: "Classification",
                fieldname: "classification",
                fieldtype: "Select",
                options: [
                    "B2B",
                    "B2BA",
                    "CDNR",
                    "CDNRA",
                    "ISD",
                    "ISDA",
                    "IMPG",
                    "IMPGSEZ",
                ],
            },
            {
                label: "Is Reverse Charge",
                fieldname: "is_reverse_charge",
                fieldtype: "Check",
            },
        ];

        fields.forEach(field => (field.parent = "Purchase Reconciliation Tool"));
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
        this.tabs.invoice_tab.$datatable.on("click", ".btn.eye", function (e) {
            const row = me.mapped_invoice_data[$(this).attr("data-name")];
            me.dm = new DetailViewDialog(me.frm, row);
        });

        this.tabs.supplier_tab.$datatable.on("click", ".btn.download", function (e) {
            const row = me.tabs.supplier_tab.data.find(
                r => r.supplier_gstin === $(this).attr("data-name")
            );
            me.export_data(row);
        });

        this.tabs.supplier_tab.$datatable.on("click", ".btn.envelope", function (e) {
            const row = me.tabs.supplier_tab.data.find(
                r => r.supplier_gstin === $(this).attr("data-name")
            );
            me.dm = new EmailDialog(me.frm, row);
        });

        this.tabs.summary_tab.$datatable.on(
            "click",
            ".match-status",
            async function (e) {
                e.preventDefault();

                const match_status = $(this).text();
                await me.filter_group.push_new_filter([
                    "Purchase Reconciliation Tool",
                    "match_status",
                    "=",
                    match_status,
                ]);
                me.filter_group.apply();
            }
        );

        this.tabs.supplier_tab.$datatable.on(
            "click",
            ".supplier-gstin",
            add_supplier_gstin_filter
        );

        this.tabs.invoice_tab.$datatable.on(
            "click",
            ".supplier-gstin",
            add_supplier_gstin_filter
        );

        async function add_supplier_gstin_filter(e) {
            e.preventDefault();

            const supplier_gstin = $(this).text().trim();
            await me.filter_group.push_new_filter([
                "Purchase Reconciliation Tool",
                "supplier_gstin",
                "=",
                supplier_gstin,
            ]);
            me.filter_group.apply();
        }
    }

    export_data(selected_row) {
        this.data_to_export = this.get_filtered_data(selected_row);
        if (selected_row) delete this.data_to_export.supplier_summary;

        const url =
            "india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool.download_excel_report";

        open_url_post(`/api/method/${url}`, {
            data: JSON.stringify(this.data_to_export),
            doc: JSON.stringify(this.frm.doc),
            is_supplier_specific: !!selected_row,
        });
    }

    get_filtered_data(selected_row = null) {
        let supplier_filter = null;

        if (selected_row) {
            supplier_filter = [
                this.frm.doctype,
                "supplier_gstin",
                "=",
                selected_row.supplier_gstin,
                false,
            ];
        }

        this.apply_filters(true, supplier_filter);

        const purchases = [];
        const inward_supplies = [];

        this.filtered_data.forEach(row => {
            if (row.inward_supply_name) inward_supplies.push(row.inward_supply_name);
            if (row.purchase_invoice_name) purchases.push(row.purchase_invoice_name);
        });

        return {
            match_summary: this.get_summary_data(),
            supplier_summary: this.get_supplier_data(),
            purchases: purchases,
            inward_supplies: inward_supplies,
        };
    }

    get_summary_data() {
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
            if (row.action != "No Action") new_row.action_taken_count += 1;
            new_row.total_docs += 1;
            new_row.tax_difference += row.tax_difference || 0;
            new_row.taxable_value_difference += row.taxable_value_difference || 0;
        });
        return Object.values(data);
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

    get_supplier_data() {
        const data = {};
        this.filtered_data.forEach(row => {
            let new_row = data[row.supplier_gstin];
            if (!new_row) {
                new_row = data[row.supplier_gstin] = {
                    supplier_name_gstin: this.get_supplier_name_gstin(row),
                    supplier_name: row.supplier_name,
                    supplier_gstin: row.supplier_gstin,
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
            if (row.action != "No Action") new_row.action_taken_count += 1;
            new_row.total_docs += 1;
            new_row.tax_difference += row.tax_difference || 0;
            new_row.taxable_value_difference += row.taxable_value_difference || 0;
        });
        return Object.values(data);
    }

    get_supplier_columns() {
        return [
            {
                label: "Supplier Name",
                fieldname: "supplier_name_gstin",
                fieldtype: "Link",
                width: 200,
            },
            {
                label: "Count <br>2A/2B Docs",
                fieldname: "inward_supply_count",
                align: "center",
                width: 120,
            },
            {
                label: "Count <br>Purchase Docs",
                fieldname: "purchase_count",
                align: "center",
                width: 120,
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_difference",
                align: "center",
                width: 150,
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_difference",
                align: "center",
                width: 150,
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "% Action <br>Taken",
                fieldname: "action_taken",
                align: "center",
                width: 120,
                _value: (...args) => {
                    return (
                        roundNumber(
                            (args[2].action_taken_count / args[2].total_docs) * 100,
                            2
                        ) + " %"
                    );
                },
            },
            {
                fieldname: "download",
                fieldtype: "html",
                width: 60,
                _value: (...args) => get_icon(...args, "download"),
            },
            {
                fieldname: "email",
                fieldtype: "html",
                width: 60,
                _value: (...args) => get_icon(...args, "envelope"),
            },
        ];
    }

    get_invoice_data() {
        this.mapped_invoice_data = {};
        this.filtered_data.forEach(row => {
            this.mapped_invoice_data[get_hash(row)] = row;
            row.supplier_name_gstin = this.get_supplier_name_gstin(row);
        });
        return this.filtered_data;
    }

    get_invoice_columns() {
        return [
            {
                fieldname: "view",
                fieldtype: "html",
                width: 60,
                align: "center",
                _value: (...args) => get_icon(...args, "eye"),
            },
            {
                label: "Supplier Name",
                fieldname: "supplier_name_gstin",
                width: 150,
            },
            {
                label: "Bill No.",
                fieldname: "bill_no",
            },
            {
                label: "Date",
                fieldname: "bill_date",
                _value: (...args) => frappe.datetime.str_to_user(args[0]),
            },
            {
                label: "Match Status",
                fieldname: "match_status",
                width: 120,
            },
            {
                label: "GST Inward <br>Supply",
                fieldname: "inward_supply_name",
                fieldtype: "Link",
                doctype: "GST Inward Supply",
                align: "center",
                width: 120,
            },
            {
                label: "Purchase <br>Invoice",
                fieldname: "purchase_invoice_name",
                fieldtype: "Link",
                doctype: "Purchase Invoice",
                align: "center",
                width: 120,
            },
            {
                fieldname: "taxable_value_difference",
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                width: 150,
                align: "center",
                _value: (...args) => {
                    return format_number(args[0]);
                },
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_difference",
                width: 120,
                align: "center",
                _value: (...args) => {
                    return format_number(args[0]);
                },
            },
            {
                fieldname: "differences",
                label: "Differences",
                width: 150,
                align: "Left",
            },
            {
                label: "Action",
                fieldname: "action",
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
        const { message } = await this.frm.call("get_invoice_details", {
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
        if (this.row.match_status == "Missing in 2A/2B")
            this.missing_doctype = "GST Inward Supply";
        else if (this.row.match_status == "Missing in PI")
            if (["IMPG", "IMPGSEZ"].includes(this.row.classification))
                this.missing_doctype = "Bill of Entry";
            else this.missing_doctype = "Purchase Invoice";
        else return [];

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
                default: [
                    this.frm.doc.purchase_from_date,
                    this.frm.doc.purchase_to_date,
                ],
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
                options:
                    this.missing_doctype == "GST Inward Supply"
                        ? ["GST Inward Supply"]
                        : ["Purchase Invoice", "Bill of Entry"],

                read_only_depends_on: `eval: ${
                    this.missing_doctype == "GST Inward Supply"
                }`,

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

    async set_link_options() {
        if (!this.dialog.get_value("doctype")) return;

        this.filters = {
            supplier_gstin: this.dialog.get_value("supplier_gstin"),
            bill_from_date: this.dialog.get_value("date_range")[0],
            bill_to_date: this.dialog.get_value("date_range")[1],
            show_matched: this.dialog.get_value("show_matched"),
            purchase_doctype: this.data.purchase_doctype,
        };

        const { message } = await this.frm.call("get_link_options", {
            doctype: this.dialog.get_value("doctype"),
            filters: this.filters,
        });

        this.dialog.get_field("link_with").set_data(message);
    }

    setup_actions() {
        // determine actions
        let actions = [];
        const doctype = this.dialog.get_value("doctype");
        if (this.row.match_status == "Missing in 2A/2B") actions.push("Link", "Ignore");
        else if (this.row.match_status == "Missing in PI")
            if (doctype == "Purchase Invoice")
                actions.push("Create", "Link", "Pending", "Ignore");
            else actions.push("Link", "Pending", "Ignore");
        else
            actions.push(
                "Unlink",
                "Accept My Values",
                "Accept Supplier Values",
                "Pending"
            );

        // setup actions
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

    _apply_custom_action(action) {
        if (action == "Unlink") {
            unlink_documents(this.frm, [this.row]);
        } else if (action == "Link") {
            purchase_reconciliation_tool.link_documents(
                this.frm,
                this.data.purchase_invoice_name,
                this.data.inward_supply_name,
                this.dialog.get_value("doctype"),
                true
            );
        } else if (action == "Create") {
            create_new_purchase_invoice(
                this.data,
                this.frm.doc.company,
                this.frm.doc.company_gstin
            );
        } else {
            apply_action(this.frm, action, [this.row]);
        }
    }

    _get_button_css(action) {
        if (action == "Unlink") return "btn-danger not-grey";
        if (action == "Pending") return "btn-secondary";
        if (action == "Ignore") return "btn-secondary";
        if (action == "Create") return "btn-primary not-grey";
        if (action == "Link") return "btn-primary not-grey btn-link disabled";
        if (action == "Accept My Values") return "btn-primary not-grey";
        if (action == "Accept Supplier Values") return "btn-primary not-grey";
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
            frappe.render_template("purchase_detail_comparision", {
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
}

class ImportDialog {
    constructor(frm, for_download = true) {
        this.frm = frm;
        this.for_download = for_download;
        this.init_dialog();
        this.dialog.show();
    }

    init_dialog() {
        if (this.for_download) this._init_download_dialog();
        else this._init_upload_dialog();

        this.return_type = this.dialog.get_value("return_type");
        this.date_range = this.dialog.get_value("date_range");
        this.setup_dialog_actions();
        this.fetch_import_history();
    }

    _init_download_dialog() {
        this.dialog = new frappe.ui.Dialog({
            title: __("Download Data from GSTN"),
            fields: [...this.get_gstr_fields(), ...this.get_history_fields()],
        });
    }

    _init_upload_dialog() {
        this.dialog = new frappe.ui.Dialog({
            title: __("Upload Data"),
            fields: [
                ...this.get_gstr_fields(),
                {
                    label: "Upload Period",
                    fieldname: "upload_period",
                    fieldtype: "Data",
                    read_only: 1,
                },
                {
                    fieldtype: "Section Break",
                },
                {
                    label: "Attach File",
                    fieldname: "attach_file",
                    fieldtype: "Attach",
                    description: "Attach .json file here",
                    options: { restrictions: { allowed_file_types: [".json"] } },
                    onchange: () => {
                        const attached_file = this.dialog.get_value("attach_file");
                        if (!attached_file) return;
                        this.update_return_period();
                    },
                },
                ...this.get_history_fields(),
            ],
        });

        this.dialog.get_field("period").toggle(false);
    }

    setup_dialog_actions() {
        if (this.for_download) {
            if (this.return_type === ReturnType.GSTR2A) {
                this.dialog.$wrapper.find(".btn-secondary").removeClass("hidden");
                this.dialog.set_primary_action(__("Download All"), () => {
                    download_gstr(this.frm, this.date_range, this.return_type, false);
                    this.dialog.hide();
                });
                this.dialog.set_secondary_action_label(__("Download Missing"));
                this.dialog.set_secondary_action(() => {
                    download_gstr(this.frm, this.date_range, this.return_type, true);
                    this.dialog.hide();
                });
            } else if (this.return_type === ReturnType.GSTR2B) {
                this.dialog.$wrapper.find(".btn-secondary").addClass("hidden");
                this.dialog.set_primary_action(__("Download"), () => {
                    download_gstr(this.frm, this.date_range, this.return_type, true);
                    this.dialog.hide();
                });
            }
        } else {
            this.dialog.set_primary_action(__("Upload"), () => {
                const file_path = this.dialog.get_value("attach_file");
                const period = this.dialog.get_value("period");
                if (!file_path) frappe.throw(__("Please select a file first!"));
                if (!period)
                    frappe.throw(
                        __(
                            "Could not fetch period from file, make sure you have selected the correct file!"
                        )
                    );
                this.upload_gstr(period, file_path);
                this.dialog.hide();
            });
        }
    }

    async fetch_import_history() {
        const { message } = await this.frm.call("get_import_history", {
            return_type: this.return_type,
            date_range: this.date_range,
            for_download: this.for_download,
        });

        if (!message) return;
        this.dialog.fields_dict.history.html(
            frappe.render_template("gstr_download_history", message)
        );
    }

    async update_return_period() {
        const file_path = this.dialog.get_value("attach_file");
        const { message } = await this.frm.call("get_return_period_from_file", {
            return_type: this.return_type,
            file_path,
        });

        if (!message) {
            this.dialog.get_field("attach_file").clear_attachment();
            frappe.throw(
                __(
                    "Please make sure you have uploaded the correct file. File Uploaded is not for {0}",
                    [this.return_type]
                )
            );
        }

        await this.dialog.set_value("upload_period", message);
        this.dialog.refresh();
    }

    upload_gstr(period, file_path) {
        this.frm.events.show_progress(this.frm, "upload");
        this.frm.call("upload_gstr", {
            return_type: this.return_type,
            period,
            file_path,
        });
    }

    get_gstr_fields() {
        return [
            {
                label: "GST Return Type",
                fieldname: "return_type",
                fieldtype: "Select",
                default: ReturnType.GSTR2B,
                options: [
                    { label: "GSTR 2A", value: ReturnType.GSTR2A },
                    { label: "GSTR 2B", value: ReturnType.GSTR2B },
                ],
                onchange: () => {
                    this.fetch_import_history();
                    this.setup_dialog_actions();
                    this.return_type = this.dialog.get_value("return_type");
                },
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: "Period",
                fieldname: "period",
                fieldtype: "Select",
                options: this.frm.get_field("inward_supply_period").df.options,
                default: this.frm.doc.inward_supply_period,
                onchange: () => {
                    const period = this.dialog.get_value("period");
                    this.frm.call("get_date_range", { period }).then(({ message }) => {
                        this.date_range =
                            message || this.dialog.get_value("date_range");
                        this.fetch_import_history();
                    });
                },
            },
            {
                label: "Date Range",
                fieldname: "date_range",
                fieldtype: "DateRange",
                default: [
                    this.frm.doc.inward_supply_from_date,
                    this.frm.doc.inward_supply_to_date,
                ],
                depends_on: "eval:doc.period == 'Custom'",
                onchange: () => {
                    this.date_range = this.dialog.get_value("date_range");
                    this.fetch_import_history();
                },
            },
        ];
    }

    get_history_fields() {
        const label = this.for_download ? "Download History" : "Upload History";

        return [
            { label, fieldtype: "Section Break" },
            { label, fieldname: "history", fieldtype: "HTML" },
        ];
    }
}

async function download_gstr(
    frm,
    date_range,
    return_type,
    only_missing = true,
    otp = null
) {
    let method;
    const args = { date_range, otp };

    if (return_type === ReturnType.GSTR2A) {
        method = "download_gstr_2a";
        args.force = !only_missing;
    } else {
        method = "download_gstr_2b";
    }

    frm.events.show_progress(frm, "download");
    const { message } = await frm.call(method, args);

    if (message && ["otp_requested", "invalid_otp"].includes(message.error_type)) {
        const otp = await india_compliance.get_gstin_otp(
            message.error_type,
            frm.doc.company_gstin
        );
        if (otp) download_gstr(frm, date_range, return_type, only_missing, otp);
    }
}

class EmailDialog {
    constructor(frm, data) {
        this.frm = frm;
        this.data = data;
        this.get_attachment();
    }

    get_attachment() {
        const export_data = this.frm.purchase_reconciliation_tool.get_filtered_data(
            this.data
        );

        frappe.call({
            method: "india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool.generate_excel_attachment",
            args: {
                data: JSON.stringify(export_data),
                doc: JSON.stringify(this.frm.doc),
            },
            callback: r => {
                this.prepare_email_args(r.message);
            },
        });
    }

    async prepare_email_args(attachment) {
        this.attachment = attachment;
        Object.assign(this, await this.get_template());
        this.recipients = await this.get_recipients();
        this.show_email_dialog();
    }

    show_email_dialog() {
        const args = {
            subject: this.subject,
            recipients: this.recipients,
            attach_document_print: false,
            message: this.message,
            attachments: this.attachment,
        };
        new frappe.views.CommunicationComposer(args);
    }
    async get_template() {
        if (!this.frm.meta.default_email_template) return {};
        let doc = {
            ...this.frm.doc,
            ...this.data,
        };

        const { message } = await frappe.call({
            method: "frappe.email.doctype.email_template.email_template.get_email_template",
            args: {
                template_name: this.frm.meta.default_email_template,
                doc: doc,
            },
        });

        return message;
    }

    async get_recipients() {
        if (!this.data) return [];

        const { message } = await frappe.call({
            method: "india_compliance.gst_india.utils.get_party_contact_details",
            args: {
                party: this.data.supplier_name,
            },
        });

        return message?.contact_email || [];
    }
}

async function fetch_date_range(frm, field_prefix, method) {
    const from_date_field = field_prefix + "_from_date";
    const to_date_field = field_prefix + "_to_date";
    const period = frm.doc[field_prefix + "_period"];
    if (!period) return;

    const { message } = await frm.call(method || "get_date_range", { period });
    if (!message) return;

    frm.set_value(from_date_field, message[0]);
    frm.set_value(to_date_field, message[1]);
}

function get_icon(value, column, data, icon) {
    /**
     * Returns custom ormated value for the row.
     * @param {string} value        Current value of the row.
     * @param {object} column       All properties of current column
     * @param {object} data         All values in its core form for current row
     * @param {string} icon         Return icon (font-awesome) as the content
     */

    const hash = get_hash(data);
    return `<button class="btn ${icon}" data-name="${hash}">
                <i class="fa fa-${icon}"></i>
            </button>`;
}

function get_hash(data) {
    if (data.purchase_invoice_name || data.inward_supply_name)
        return data.purchase_invoice_name + "~" + data.inward_supply_name;
    if (data.supplier_gstin) return data.supplier_gstin;
}

function patch_set_active_tab(frm) {
    const set_active_tab = frm.set_active_tab;
    frm.set_active_tab = function (...args) {
        set_active_tab.apply(this, args);
        frm.refresh();
    };
}

purchase_reconciliation_tool.link_documents = async function (
    frm,
    purchase_invoice_name,
    inward_supply_name,
    link_doctype,
    alert = true
) {
    if (frm.get_active_tab()?.df.fieldname != "invoice_tab") return;

    // link documents & update data.
    const { message: r } = await frm.call("link_documents", {
        purchase_invoice_name,
        inward_supply_name,
        link_doctype,
    });
    const reco_tool = frm.purchase_reconciliation_tool;
    const new_data = reco_tool.data.filter(
        row =>
            !(
                row.purchase_invoice_name == purchase_invoice_name ||
                row.inward_supply_name == inward_supply_name
            )
    );
    new_data.push(...r);

    reco_tool.refresh(new_data);
    if (alert)
        after_successful_action(frm.purchase_reconciliation_tool.tabs.invoice_tab);
};

async function unlink_documents(frm, selected_rows) {
    if (frm.get_active_tab()?.df.fieldname != "invoice_tab") return;
    const { invoice_tab } = frm.purchase_reconciliation_tool.tabs;
    if (!selected_rows) selected_rows = invoice_tab.get_checked_items();

    if (!selected_rows.length)
        return frappe.show_alert({
            message: __("Please select rows to unlink"),
            indicator: "red",
        });

    // validate selected rows
    selected_rows.forEach(row => {
        if (row.match_status.includes("Missing"))
            frappe.throw(
                __(
                    "You have selected rows where no match is available. Please remove them before unlinking."
                )
            );
    });

    // unlink documents & update table
    const { message: r } = await frm.call("unlink_documents", selected_rows);
    const unlinked_docs = get_unlinked_docs(selected_rows);

    const reco_tool = frm.purchase_reconciliation_tool;
    const new_data = reco_tool.data.filter(
        row =>
            !(
                unlinked_docs.has(row.purchase_invoice_name) ||
                unlinked_docs.has(row.inward_supply_name)
            )
    );
    new_data.push(...r);
    reco_tool.refresh(new_data);
    after_successful_action(invoice_tab);
}

function get_unlinked_docs(selected_rows) {
    const unlinked_docs = new Set();
    selected_rows.forEach(row => {
        unlinked_docs.add(row.purchase_invoice_name);
        unlinked_docs.add(row.inward_supply_name);
    });

    return unlinked_docs;
}

function deepcopy(array) {
    return JSON.parse(JSON.stringify(array));
}

function apply_action(frm, action, selected_rows) {
    const active_tab = frm.get_active_tab()?.df.fieldname;
    if (!active_tab) return;

    const tab = frm.purchase_reconciliation_tool.tabs[active_tab];
    if (!selected_rows) selected_rows = tab.get_checked_items();

    // get affected rows
    const { filtered_data, data } = frm.purchase_reconciliation_tool;
    let affected_rows = get_affected_rows(active_tab, selected_rows, filtered_data);

    if (!affected_rows.length)
        return frappe.show_alert({
            message: __("Please select rows to apply action"),
            indicator: "red",
        });

    // validate affected rows
    if (action.includes("Accept")) {
        let warn = false;
        affected_rows = affected_rows.filter(row => {
            if (row.match_status.includes("Missing")) {
                warn = true;
                return false;
            }
            return true;
        });

        if (warn)
            frappe.msgprint(
                __(
                    "You can only Accept values where a match is available. Rows where match is missing will be ignored."
                )
            );
    } else if (action == "Ignore") {
        let warn = false;
        affected_rows = affected_rows.filter(row => {
            if (!row.match_status.includes("Missing")) {
                warn = true;
                return false;
            }
            return true;
        });

        if (warn)
            frappe.msgprint(
                __(
                    "You can only apply <strong>Ignore</strong> action on rows where data is Missing in 2A/2B or Missing in PI. These rows will be ignored."
                )
            );
    }

    // update affected rows to backend and frontend
    frm.call("apply_action", { data: affected_rows, action });
    const new_data = data.filter(row => {
        if (has_matching_row(row, affected_rows)) row.action = action;
        return true;
    });

    frm.purchase_reconciliation_tool.refresh(new_data);
    after_successful_action(tab);
}

function after_successful_action(tab) {
    if (tab) tab.clear_checked_items();
    frappe.show_alert({
        message: "Action applied successfully",
        indicator: "green",
    });
}

function has_matching_row(row, array) {
    return array.filter(item => JSON.stringify(item) === JSON.stringify(row)).length;
}

function get_affected_rows(tab, selection, data) {
    if (tab == "invoice_tab") return selection;

    if (tab == "supplier_tab")
        return data.filter(
            inv =>
                selection.filter(row => row.supplier_gstin == inv.supplier_gstin).length
        );

    if (tab == "summary_tab")
        return data.filter(
            inv => selection.filter(row => row.match_status == inv.match_status).length
        );
}

async function create_new_purchase_invoice(row, company, company_gstin) {
    if (row.match_status != "Missing in PI") return;
    const doc = row._inward_supply;

    const { message: supplier } = await frappe.call({
        method: "india_compliance.gst_india.utils.get_party_for_gstin",
        args: {
            gstin: row.supplier_gstin,
        },
    });

    let company_address;
    await frappe.model.get_value(
        "Address",
        { gstin: company_gstin, is_your_company_address: 1 },
        "name",
        r => (company_address = r.name)
    );

    frappe.route_hooks.after_load = frm => {
        function _set_value(values) {
            for (const key in values) {
                if (values[key] == frm.doc[key]) continue;
                frm.set_value(key, values[key]);
            }
        }

        const values = {
            company: company,
            bill_no: doc.bill_no,
            bill_date: doc.bill_date,
            is_reverse_charge: ["Yes", 1].includes(doc.is_reverse_charge) ? 1 : 0,
        };

        _set_value({
            ...values,
            supplier: supplier,
            shipping_address: company_address,
            billing_address: company_address,
        });

        // validated this on save
        frm._inward_supply = {
            ...values,
            name: row.inward_supply_name,
            company_gstin: company_gstin,
            inward_supply: row.inward_supply,
            supplier_gstin: row.supplier_gstin,
            place_of_supply: doc.place_of_supply,
            cgst: doc.cgst,
            sgst: doc.sgst,
            igst: doc.igst,
            cess: doc.cess,
            taxable_value: doc.taxable_value,
        };
    };

    frappe.new_doc("Purchase Invoice");
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
