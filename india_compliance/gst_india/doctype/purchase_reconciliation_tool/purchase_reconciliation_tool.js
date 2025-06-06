// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

const DOCTYPE = "Purchase Reconciliation Tool";
const tooltip_info = {
    purchase_period: "Returns purchases during this period where no match is found.",
    inward_supply_period:
        "Returns all documents from GSTR 2A/2B during this return period.",
};

const api_enabled = india_compliance.is_api_enabled();
const GST_CATEGORIES = ["B2B", "B2BA", "CDNR", "CDNRA", "ISD", "IMPG", "IMPGSEZ"];
const ALERT_HTML = `
    <div class="gstr2b-alert alert alert-primary fade show d-flex align-items-center justify-content-between border-0" role="alert">
        <div>
            You have missing GSTR-2B downloads
        </div>
        ${
            api_enabled
                ? `<a id="download-gstr2b-button" href="#" class="alert-link">
                    Download 2B
                </a>`
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
                frm.doc.company_gstin,
                null,
                true
            );
            remove_gstr2b_alert(existing_alert);
        });
}

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        patch_set_active_tab(frm);
        new india_compliance.quick_info_popover(frm, tooltip_info);

        await frappe.require("purchase_reconciliation_tool.bundle.js");
        frm.trigger("company");
        frm.reconciliation_tabs = new PurchaseReconciliationTool(
            frm,
            ["invoice", "supplier", "summary"],
            "reconciliation_html"
        );

        frm.events.handle_download_message(frm);
        frm.events.handle_regeneration_and_redownload(frm);
    },

    onload(frm) {
        add_gstr2b_alert(frm);

        frm.trigger("purchase_period");
        frm.trigger("inward_supply_period");
    },

    refresh(frm) {
        frm.reco_tool_actions = new PurchaseReconciliationToolAction(frm);
        frm.reco_tool_actions.setup_actions();
    },

    async company(frm) {
        render_empty_state(frm);
        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm, true);

        frm.set_value("company_gstin", options[0]);
    },

    async company_gstin(frm) {
        render_empty_state(frm);
        await fetch_date_range(
            frm,
            "inward_supply",
            "get_date_range_and_check_missing_documents"
        );
        add_gstr2b_alert(frm);
    },

    async purchase_period(frm) {
        render_empty_state(frm);
        await fetch_date_range(frm, "purchase");
        set_date_range_description(frm, "purchase");
    },

    async inward_supply_period(frm) {
        render_empty_state(frm);
        await fetch_date_range(
            frm,
            "inward_supply",
            "get_date_range_and_check_missing_documents"
        );
        set_date_range_description(frm, "inward_supply");
        add_gstr2b_alert(frm);
    },

    gst_return: render_empty_state,

    include_ignored: render_empty_state,

    show_progress(frm, type) {
        if (type == "download") {
            frappe.run_serially([
                () => frm.events.update_progress(frm, "update_2a_2b_api_progress"),
                () =>
                    frm.events.update_progress(
                        frm,
                        "update_2a_2b_transactions_progress"
                    ),
            ]);
        } else if (type == "upload") {
            frm.events.update_progress(frm, "update_2a_2b_transactions_progress");
        }
    },

    update_progress(frm, method) {
        frappe.realtime.on(method, data => {
            const { current_progress } = data;
            const message =
                method == "update_2a_2b_api_progress"
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
                method != "update_2a_2b_api_progress" &&
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

    handle_download_message(frm) {
        frappe.realtime.on("gstr_2a_2b_download_message", message => {
            frm.dashboard.hide();
            frappe.msgprint(message);
        });
    },

    handle_regeneration_and_redownload(frm) {
        frappe.realtime.on("regenerate_gstr_2b", args => {
            // This has to be done because frm is refreshed after download completes
            setTimeout(() => {
                frappe.show_alert({
                    message: __(
                        "GSTR 2B download for period {0} is in progress, due to pending regeneration.",
                        [args.return_period]
                    ),
                    indicator: "orange",
                });

                gstr_2b.regenerate({
                    gstin: args.gstin,
                    return_period: args.return_period,
                    callback: frm.events.check_regeneration_status_and_redownload,
                    frm: frm,
                    doctype: DOCTYPE,
                });
            }, 1000);
        });
    },

    check_regeneration_status_and_redownload(regeneration_status, args) {
        if (regeneration_status.status === "ER") {
            frappe.msgprint({
                message: __(regeneration_status.error),
                indicator: "red",
            });
        } else if (regeneration_status.status === "P") {
            download_gstr(
                args.frm,
                null,
                ReturnType.GSTR2B,
                args.gstin,
                args.return_period
            );
        }
    },
});

class PurchaseReconciliationTool extends reconciliation.reconciliation_tabs {
    get_tab_group_fields() {
        return [
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
        ];
    }

    get_filter_fields() {
        const fields = super.get_filter_fields();
        fields.push(
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
                options: ["No Action", "Accept", "Ignore", "Pending"],
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
            {
                label: "DocType",
                fieldname: "purchase_doctype",
                fieldtype: "Select",
                options: ["Purchase Invoice", "Bill of Entry"],
            }
        );

        fields.forEach(field => (field.parent = DOCTYPE));
        return fields;
    }

    set_listeners() {
        const me = this;
        this.tabs.invoice_tab.datatable.$datatable.on(
            "click",
            ".btn.eye",
            function (e) {
                const row = me.mapped_invoice_data[$(this).attr("data-name")];
                me.dm = new DetailViewDialog(me.frm, row);
            }
        );

        this.tabs.supplier_tab.datatable.$datatable.on(
            "click",
            ".btn.download",
            function (e) {
                const row = me.tabs.supplier_tab.datatable.data.find(
                    r => r.supplier_gstin === $(this).attr("data-name")
                );
                me.frm.reco_tool_actions.export_data(row);
            }
        );

        this.tabs.supplier_tab.datatable.$datatable.on(
            "click",
            ".btn.envelope",
            function (e) {
                const row = me.tabs.supplier_tab.datatable.data.find(
                    r => r.supplier_gstin === $(this).attr("data-name")
                );
                me.dm = new EmailDialog(me.frm, row);
            }
        );

        const filter_map = {
            // TAB: { SELECTOR: FIELDNAME }
            summary: { ".match-status": "match_status" },
            supplier: { ".supplier-gstin": "supplier_gstin" },
            invoice: {
                ".match-status": "match_status",
                ".action-performed": "action",
                ".supplier-gstin": "supplier_gstin",
            },
        };

        Object.keys(filter_map).forEach(tab => {
            Object.keys(filter_map[tab]).forEach(selector => {
                this.tabs[`${tab}_tab`].datatable.$datatable.on(
                    "click",
                    selector,
                    async function (e) {
                        e.preventDefault();

                        await me.filter_group.add_or_remove_filter([
                            DOCTYPE,
                            filter_map[tab][selector],
                            "=",
                            $(this).text().trim(),
                        ]);
                        me.filter_group.apply();
                    }
                );
            });
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
                _value: (...args) => {
                    return `<a href="#" class='match-status'>${args[0]}</a>`;
                },
            },
            {
                label: "GST Inward <br>Supply",
                fieldname: "inward_supply_name",
                fieldtype: "Link",
                options: "GST Inward Supply",
                align: "center",
                width: 120,
                _after_format: (...args) => this.get_value_with_indicator(...args),
            },
            {
                label: "Purchase <br>Invoice",
                fieldname: "purchase_invoice_name",
                fieldtype: "Dynamic Link",
                options: "purchase_doctype",
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
                _value: (...args) => {
                    return `<a href="#" class='action-performed'>${args[0]}</a>`;
                },
            },
        ];
    }
}

class PurchaseReconciliationToolAction {
    constructor(frm) {
        this.frm = frm;
    }

    setup_actions() {
        this.setup_document_actions();
        this.setup_row_actions();
    }

    setup_document_actions() {
        // Primary Action
        this.frm.disable_save();
        this.frm.page.set_primary_action(__("Generate"), async () => {
            if (!this.frm.doc.company && !this.frm.doc.company_gstin) {
                frappe.throw(
                    __("Please provide either a Company name or Company GSTIN.")
                );
            }

            this.get_reconciliation_data(this.frm);
        });

        // Download Button
        api_enabled
            ? this.frm.add_custom_button(
                  __("Download 2A/2B"),
                  () => new ImportDialog(this.frm)
              )
            : this.frm.add_custom_button(
                  __("Upload 2A/2B"),
                  () => new ImportDialog(this.frm, false)
              );

        // Export button
        this.frm.add_custom_button(__("Export"), () => this.export_data());
    }

    setup_row_actions() {
        const action_group = __("Actions");

        if (!this.frm.reconciliation_tabs?.data?.length) return;
        if (this.frm.get_active_tab()?.df.fieldname == "invoice_tab") {
            this.frm.add_custom_button(
                __("Unlink"),
                () => reconciliation.unlink_documents(this.frm),
                action_group
            );
            this.frm.add_custom_button(__("dropdown-divider"), () => {}, action_group);
        }

        // Setup Actions
        ["Accept", "Pending", "Ignore"].forEach(action =>
            this.frm.add_custom_button(
                __(action),
                () => apply_action(this.frm, action),
                action_group
            )
        );

        // Add Dropdown Divider to differentiate between Actions
        this.frm.$wrapper
            .find("[data-label='dropdown-divider']")
            .addClass("dropdown-divider");

        // move actions button next to filters
        for (const group_div of $(".custom-actions .inner-group-button")) {
            const btn_label = group_div.querySelector("button").innerText?.trim();
            if (btn_label != action_group) continue;

            $(".custom-button-group .inner-group-button").remove();

            // to hide `Actions` button group on smaller screens
            $(group_div).addClass("hidden-md");

            $(group_div).appendTo(this.frm.$wrapper.find(".custom-button-group"));
        }
    }

    async get_reconciliation_data(frm) {
        const { message } = await frm._call("reconcile_and_generate_data");

        frm.__reconciliation_data = message;

        frm.reconciliation_tabs.render_data(frm.__reconciliation_data);
        frm.doc.data_state = message.length ? "available" : "unavailable";

        // Toggle HTML fields
        frm.refresh();
    }

    export_data(selected_row) {
        const data_to_export =
            this.frm.reconciliation_tabs.get_filtered_data(selected_row);
        if (selected_row) delete data_to_export.supplier_summary;

        const url =
            "india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool.download_excel_report";

        open_url_post(`/api/method/${url}`, {
            data: JSON.stringify(data_to_export),
            doc: JSON.stringify(this.frm.doc),
            is_supplier_specific: !!selected_row,
        });
    }
}

class DetailViewDialog extends reconciliation.detail_view_dialog {
    _get_custom_actions() {
        const doctype = this.dialog.get_value("doctype");
        if (this.row.match_status == "Missing in 2A/2B") return ["Link", "Ignore"];
        else if (this.row.match_status == "Missing in PI")
            if (doctype == "Purchase Invoice")
                return ["Create", "Link", "Pending", "Ignore"];
            else return ["Link", "Pending", "Ignore"];
        else return ["Unlink", "Accept", "Pending"];
    }

    _apply_custom_action(action) {
        if (action == "Unlink") {
            reconciliation.unlink_documents(this.frm, [this.row]);
        } else if (action == "Link") {
            reconciliation.link_documents(
                this.frm,
                this.data.purchase_invoice_name,
                this.data.inward_supply_name,
                this.data.purchase_doctype,
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
            apply_action(this.frm, action, [this.row]);
        }
    }

    _get_button_css(action) {
        if (action == "Unlink") return "btn-danger not-grey";
        if (action == "Pending") return "btn-secondary";
        if (action == "Ignore") return "btn-secondary";
        if (action == "Create") return "btn-primary not-grey";
        if (action == "Link") return "btn-primary not-grey btn-link disabled";
        if (action == "Accept") return "btn-primary not-grey";
    }

    _set_missing_doctype() {
        if (this.row.match_status == "Missing in 2A/2B")
            this.missing_doctype = "GST Inward Supply";
        else if (this.row.match_status == "Missing in PI")
            if (["IMPG", "IMPGSEZ"].includes(this.row.classification))
                this.missing_doctype = "Bill of Entry";
            else this.missing_doctype = "Purchase Invoice";
        else return;

        if (this.missing_doctype == "GST Inward Supply")
            this.doctype_options = ["GST Inward Supply"];
        else this.doctype_options = ["Purchase Invoice", "Bill of Entry"];
    }

    _get_default_date_range() {
        return [this.frm.doc.purchase_from_date, this.frm.doc.purchase_to_date];
    }
}

class ImportDialog {
    constructor(frm, for_download = true) {
        this.frm = frm;
        this.for_download = for_download;
        this.company_gstin = frm.doc.company_gstin;
        this.init_dialog();
        this.dialog.show();
    }

    init_dialog() {
        if (!this.frm.doc.company) {
            frappe.throw(__("Please select a Company first!"));
        }

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
            fields: [
                ...this.get_gstr_fields(),
                ...this.get_2a_category_fields(),
                ...this.get_fields_for_pending_downloads(),
                ...this.get_fields_for_download_history(),
            ],
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
                ...this.get_fields_for_pending_downloads(),
                ...this.get_fields_for_download_history(),
            ],
        });

        this.dialog.get_field("period").toggle(false);
    }

    setup_dialog_actions() {
        if (this.for_download) {
            if (this.return_type === ReturnType.GSTR2A) {
                this.dialog.set_primary_action(__("Download All"), () => {
                    this.download_gstr_by_category(false);
                });
                this.dialog.set_secondary_action_label(__("Download Missing"));
                this.dialog.set_secondary_action(() => {
                    this.download_gstr_by_category(true);
                });
            } else if (this.return_type === ReturnType.GSTR2B) {
                this.dialog.set_primary_action(__("Download All"), () => {
                    this.download_gstr_by_period(false);
                });
                this.dialog.set_secondary_action_label(__("Download Missing"));
                this.dialog.set_secondary_action(() => {
                    this.download_gstr_by_period(true);
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

    download_gstr_by_category(only_missing) {
        const marked_gst_categories = GST_CATEGORIES.filter(
            category => this.dialog.fields_dict[category].value === 1
        );
        if (marked_gst_categories.length === 0) {
            frappe.throw(__("Please select at least one Category to Download"));
        }
        download_gstr(
            this.frm,
            this.date_range,
            this.return_type,
            this.company_gstin,
            null,
            only_missing,
            marked_gst_categories
        );
        this.dialog.hide();
    }

    download_gstr_by_period(only_missing) {
        if (only_missing && this.has_no_pending_download) {
            frappe.msgprint({
                message: "There are no pending downloads for the selected period.",
                title: "No Pending Downloads",
                indicator: "orange",
            });
            return;
        }

        download_gstr(
            this.frm,
            this.date_range,
            this.return_type,
            this.company_gstin,
            null,
            only_missing
        );

        this.dialog.hide();
    }

    async fetch_import_history() {
        if (!this.company_gstin) return;

        // fetch history
        const { message } = await this.frm._call("get_import_history", {
            company_gstin: this.company_gstin,
            return_type: this.return_type,
            date_range: this.date_range,
            for_download: this.for_download,
        });

        // ensure sequence is maintained
        function get_map(message) {
            return Array.isArray(message) ? new Map(message) : message;
        }

        const _pending = get_map(message.pending_download);
        const _history = get_map(message.download_history);

        // render html
        let pending_download = { columns: ["Period", "GSTIN"], data: _pending };
        this.dialog.fields_dict.pending_download.html(
            frappe.render_template("gstr_download_history", pending_download)
        );

        let download_history = { columns: ["Period", "Downloaded On"], data: _history };
        let html =
            this.company_gstin === "All"
                ? ""
                : frappe.render_template("gstr_download_history", download_history);

        this.dialog.fields_dict.history.html(html);

        // flag
        this.has_no_pending_download = typeof message.pending_download == "string";
    }

    async update_return_period() {
        const file_path = this.dialog.get_value("attach_file");
        const { message } = await this.frm._call("get_return_period_from_file", {
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
        this.frm._call("upload_gstr", {
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
                    this.return_type = this.dialog.get_value("return_type");
                    this.fetch_import_history();
                    this.setup_dialog_actions();
                },
            },
            {
                label: "Company GSTIN",
                fieldname: "company_gstin",
                fieldtype: "Autocomplete",
                default: this.frm.doc.company_gstin,
                get_query: async () => {
                    let { message: gstin_list } = await frappe.call({
                        method: "india_compliance.gst_india.utils.get_gstin_list",
                        args: { party: this.frm.doc.company },
                    });

                    gstin_list.unshift("All");
                    this.dialog.fields_dict.company_gstin.set_data(gstin_list);
                },
                onchange: () => {
                    this.company_gstin = this.dialog.get_value("company_gstin");
                    this.fetch_import_history();
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
                onchange: async () => {
                    const period = this.dialog.get_value("period");
                    const { message } = await this.frm._call("get_date_range", {
                        period,
                    });

                    this.date_range = message || this.dialog.get_value("date_range");
                    this.fetch_import_history();
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

    get_2a_category_fields() {
        const fields = [];
        const section_field = {
            fieldtype: "Section Break",
            depends_on: "eval:doc.return_type == 'GSTR2a'",
        };

        const import_categories = ["IMPG", "IMPGSEZ"];
        const rare_categories = ["ISD"];
        const overseas_enabled = gst_settings.enable_overseas_transactions;

        fields.push(section_field);
        GST_CATEGORIES.forEach((category, i) => {
            let default_check = true;
            if (rare_categories.includes(category)) default_check = false;
            else if (import_categories.includes(category) && !overseas_enabled)
                default_check = false;

            fields.push({
                label: category,
                fieldname: category,
                fieldtype: "Check",
                default: default_check,
            });

            // after every 4 fields section break
            if (i % 4 === 3) fields.push({ ...section_field, hide_border: true });
            else fields.push({ fieldtype: "Column Break" });
        });

        return fields;
    }

    get_fields_for_pending_downloads() {
        const label = this.for_download ? "🟠 Pending Download" : "🟠 Pending Upload";
        return [
            { label, fieldtype: "Section Break", depends_on: "eval:doc.company_gstin" },
            { label, fieldname: "pending_download", fieldtype: "HTML" },
        ];
    }

    get_fields_for_download_history() {
        const label = this.for_download ? "🟢 Download History" : "🟢 Upload History";

        return [
            {
                label,
                fieldtype: "Section Break",
                depends_on: "eval:doc.company_gstin && doc.company_gstin != 'All'",
            },
            { label, fieldname: "history", fieldtype: "HTML" },
        ];
    }
}

async function download_gstr(
    frm,
    date_range,
    return_type,
    company_gstin,
    return_period,
    only_missing = true,
    gst_categories = null
) {
    let company_gstins;
    if (company_gstin == "All")
        company_gstins = await india_compliance.get_gstin_options(frm.doc.company);
    else company_gstins = [company_gstin];

    company_gstins.forEach(async gstin => {
        const args = {
            return_type,
            company_gstin: gstin,
            date_range,
            return_period,
            force: !only_missing,
            gst_categories,
        };
        frm.events.show_progress(frm, "download");
        await frm.taxpayer_api_call("download_gstr", args);
    });
}

class EmailDialog {
    constructor(frm, data) {
        this.frm = frm;
        this.data = data;
        this.get_attachment();
    }

    get_attachment() {
        const export_data = this.frm.reconciliation_tabs.get_filtered_data(this.data);

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
    if (!period || period == "Custom") return;

    const { message } = await frm._call(method || "get_date_range", { period });

    frm.set_value(from_date_field, message[0]);
    frm.set_value(to_date_field, message[1]);
}

function set_date_range_description(frm, field_prefixes) {
    if (!field_prefixes) field_prefixes = ["inward_supply", "purchase"];
    else field_prefixes = [field_prefixes];

    field_prefixes.forEach(prefix => {
        const period_field = prefix + "_period";
        const period = frm.doc[period_field];

        if (!period || period == "Custom")
            return frm.get_field(period_field).set_description("");

        const from_date = frappe.datetime.str_to_user(frm.doc[prefix + "_from_date"]);
        const to_date = frappe.datetime.str_to_user(frm.doc[prefix + "_to_date"]);
        frm.get_field(period_field).set_description(`${from_date} to ${to_date}`);
    });
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

function deepcopy(array) {
    return JSON.parse(JSON.stringify(array));
}

function apply_action(frm, action, selected_rows) {
    const active_tab = frm.get_active_tab()?.df.fieldname;
    if (!active_tab) return;

    const tab = frm.reconciliation_tabs.tabs[active_tab];
    if (!selected_rows) selected_rows = tab.datatable.get_checked_items();

    // get affected rows
    const { filtered_data, data } = frm.reconciliation_tabs;
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
    } else if (action == "Pending") {
        let warn = false;
        affected_rows = affected_rows.filter(row => {
            if (row.match_status == "Missing in 2A/2B") {
                warn = true;
                return false;
            }
            return true;
        });

        if (warn)
            frappe.msgprint(
                __(
                    "You cannot apply <strong>Pending</strong> action on rows where data is Missing in 2A/2B. These rows will be ignored."
                )
            );
    }

    if (!affected_rows.length) return;

    // update affected rows to backend and frontend
    frm._call("apply_action", { data: affected_rows, action });

    const new_data = data.filter(row => {
        if (has_matching_row(row, affected_rows)) row.action = action;
        return true;
    });

    frm.reconciliation_tabs.refresh(new_data);
    reconciliation.after_successful_action(tab);
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

function render_empty_state(frm) {
    frm.__reconciliation_data = null;
    frm.doc.data_state = null;

    frm.refresh();
}
