// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

const api_enabled = india_compliance.is_api_enabled();
const DOCTYPE = "GST Invoice Management System";
const DOC_PATH =
    "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system";

const category_map = {
    "B2B-Invoices": "Invoice",
    "B2B-Credit Notes": "Credit Note",
    "B2B-Debit Notes": "Debit Note",
};

const ACTION_MAP = {
    "No Action": "No Action",
    Accept: "Accepted",
    Pending: "Pending",
    Reject: "Rejected",
};

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        await frappe.require("ims.bundle.js");

        frm.reconciliation_tabs = new IMS(
            frm,
            ["invoice", "match_summary", "action_summary"],
            "invoice_html"
        );

        frm.trigger("company");

        // Setup Listeners

        // Download Queued
        frappe.realtime.on("ims_download_queued", message => {
            frappe.msgprint(message["message"]);
        });

        // Downloaded and Reconciled Invoices
        frappe.realtime.on("ims_download_completed", message => {
            frm.ims_actions.get_ims_data();
            frappe.show_alert({ message: message["message"], indicator: "green" });
        });

        // Upload and Check Status
        frappe.realtime.on("upload_data_and_check_status", async message => {
            await frm.ims_actions.get_ims_data();
            frm.ims_actions.upload_ims_data();
        });
    },

    async company(frm) {
        render_empty_state(frm);
        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);
        frm.set_value("company_gstin", options[0]);

        set_period_options(frm);
    },

    company_gstin(frm) {
        render_empty_state(frm);
        set_period_options(frm);
    },

    period: render_empty_state,

    refresh(frm) {
        show_download_invoices_message(frm);

        frm.ims_actions = new IMSAction(frm);
        frm.ims_actions.setup_actions();
    },
});

class IMS extends reconciliation.reconciliation_tabs {
    render_data(data) {
        this.process_data(data);
        super.render_data(data);
    }

    refresh(data) {
        this.process_data(data);
        super.refresh(data);
        this.set_actions_summary();
    }

    get_tab_group_fields() {
        return [
            {
                //hack: for the FieldGroup(Layout) to avoid rendering default "details" tab
                fieldtype: "Section Break",
            },
            {
                label: "Match Summary",
                fieldtype: "Tab Break",
                fieldname: "match_summary_tab",
                active: 1,
            },
            {
                fieldtype: "HTML",
                fieldname: "match_summary_data",
            },
            {
                label: "Actions Summary",
                fieldtype: "Tab Break",
                fieldname: "action_summary_tab",
            },
            {
                fieldtype: "HTML",
                fieldname: "action_summary_data",
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
                    "Missing in PI",
                    "Suggested Mark as Pending",
                ],
            },
            {
                label: "Action",
                fieldname: "ims_action",
                fieldtype: "Select",
                options: ["No Action", "Accepted", "Rejected", "Pending"],
            },
            {
                label: "Document Type",
                fieldname: "doc_type",
                fieldtype: "Select",
                options: ["Invoice", "Credit Note", "Debit Note"],
            },
            {
                label: "Upload Pending",
                fieldname: "pending_upload",
                fieldtype: "Check",
            },
            {
                label: "Is Pending Action Allowed",
                fieldname: "is_pending_action_allowed",
                fieldtype: "Check",
            },
            {
                label: "Classification",
                fieldname: "classification",
                fieldtype: "Select",
                options: ["B2B", "B2BA", "CDNR", "CDNRA"],
            },
            {
                label: "Is Supplier Return Filed",
                fieldname: "is_supplier_return_filed",
                fieldtype: "Check",
            }
        );

        fields.forEach(field => (field.parent = DOCTYPE));
        return fields;
    }

    set_listeners() {
        const me = this;

        // TODO: Refactor like purchase_reconciliation.js

        this.tabs.invoice_tab.datatable.$datatable.on(
            "click",
            ".supplier-gstin",
            function (e) {
                me.update_filter(e, "supplier_gstin", $(this).text().trim(), me);
            }
        );

        this.tabs.invoice_tab.datatable.$datatable.on(
            "click",
            ".match-status",
            function (e) {
                me.update_filter(e, "match_status", $(this).text(), me);
            }
        );

        this.tabs.match_summary_tab.datatable.$datatable.on(
            "click",
            ".match-status",
            function (e) {
                me.update_filter(e, "match_status", $(this).text(), me);
            }
        );

        this.tabs.invoice_tab.datatable.$datatable.on(
            "click",
            ".ims-action",
            function (e) {
                me.update_filter(e, "ims_action", $(this).text(), me);
            }
        );

        this.tabs.action_summary_tab.datatable.$datatable.on(
            "click",
            ".invoice-category",
            function (e) {
                me.update_filter(e, "doc_type", category_map[$(this).text()], me);
            }
        );

        this.tabs.invoice_tab.datatable.$datatable.on(
            "click",
            ".classification",
            function (e) {
                me.update_filter(e, "classification", $(this).text(), me);
            }
        );

        this.tabs.invoice_tab.datatable.$datatable.on(
            "click",
            ".btn.eye",
            function (e) {
                const row = me.mapped_invoice_data[$(this).attr("data-name")];
                me.dm = new DetailViewDialog(me.frm, row);
            }
        );
    }

    async update_filter(e, field, field_value, me) {
        e.preventDefault();

        await me.filter_group.add_or_remove_filter([DOCTYPE, field, "=", field_value]);
        me.filter_group.apply();
    }

    get_match_summary_columns() {
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

    get_match_summary_data() {
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
                width: 200,
            },
            {
                label: "Bill No.",
                fieldname: "bill_no_date",
                align: "center",
                width: 120,
            },
            {
                label: "Match Status",
                fieldname: "match_status",
                align: "center",
                width: 120,
                _value: (...args) => `<a href="#" class='match-status'>${args[0]}</a>`,
            },
            {
                label: "Action",
                fieldname: "ims_action",
                align: "center",
                width: 100,
                _value: (...args) => `<a href="#" class='ims-action'>${args[0]}</a>`,
            },
            {
                label: "GST Inward <br>Supply",
                fieldname: "inward_supply_name",
                align: "center",
                fieldtype: "Link",
                options: "GST Inward Supply",
                width: 150,
                _after_format: (...args) => this.get_value_with_indicator(...args),
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
                label: "Posting Date",
                fieldname: "posting_date",
                align: "center",
                width: 120,
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_difference",
                align: "center",
                width: 150,
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_difference",
                align: "center",
                width: 160,
                _value: (...args) => format_number(args[0]),
            },
            {
                label: "Classification",
                fieldname: "classification",
                align: "center",
                width: 100,
                _value: (...args) =>
                    `<a href="#" class='classification'>${args[0]}</a>`,
            },
        ];
    }

    get_invoice_data() {
        if (!this.data.length) return [];

        const data = [];
        this.mapped_invoice_data = {};

        this.filtered_data.forEach(row => {
            this.mapped_invoice_data[row.inward_supply_name] = row;

            data.push({
                supplier_name_gstin: this.get_supplier_name_gstin(row),
                bill_no_date: this.get_bill_no_bill_date(row),
                classification: row._inward_supply.classification,
                ims_action: row.ims_action || "",
                match_status: row.match_status,
                linked_doc: row.purchase_invoice_name,
                tax_difference: row.tax_difference,
                taxable_value_difference: row.taxable_value_difference,
                inward_supply_name: row.inward_supply_name,
                pending_upload: row.pending_upload,
                is_supplier_return_filed: row.is_supplier_return_filed,
                linked_voucher_type: row._purchase_invoice.doctype,
                posting_date: row.posting_date,
            });
        });

        return data;
    }

    get_action_summary_columns() {
        return [
            {
                label: "Category",
                fieldname: "category",
                width: 200,
                _value: (...args) =>
                    `<a href="#" class='invoice-category'>${args[0]}</a>`,
            },
            {
                label: "No Action",
                fieldname: "no_action",
                width: 200,
            },
            {
                label: "Accepted",
                fieldname: "accepted",
                width: 200,
            },
            {
                label: "Pending",
                fieldname: "pending",
                width: 200,
            },
            {
                label: "Rejected",
                fieldname: "rejected",
                width: 200,
            },
        ];
    }

    get_action_summary_data(data) {
        const category_map = {
            Invoice: "B2B-Invoices",
            "Credit Note": "B2B-Credit Notes",
            "Debit Note": "B2B-Debit Notes",
        };
        let summary_data = {};
        if (!data) data = this.filtered_data;

        data.forEach(row => {
            const action = frappe.scrub(row.ims_action);
            const category = category_map[row.doc_type];
            if (!summary_data[category]) {
                summary_data[category] = {
                    category,
                    no_action: 0,
                    accepted: 0,
                    rejected: 0,
                    pending: 0,
                };
            }
            summary_data[category][action] += 1;
        });

        return Object.values(summary_data);
    }

    async set_actions_summary() {
        const actions_data = this.get_action_summary_data(this.data);

        if ($(".action-performed-summary").length) {
            $(".action-performed-summary").remove();
        }

        $(function () {
            $('[data-toggle="tooltip"]').tooltip();
        });

        const actions_summary = {
            no_action: { count: 0, color: "#7c7c7c" },
            accepted: { count: 0, color: "#28a745" },
            pending: { count: 0, color: "#ffc107" },
            rejected: { count: 0, color: "#e03636" },
        };

        actions_data.forEach(row => {
            actions_summary.accepted.count += row.accepted;
            actions_summary.pending.count += row.pending;
            actions_summary.rejected.count += row.rejected;
            actions_summary.no_action.count += row.no_action;
        });

        const action_performed_cards = Object.entries(actions_summary)
            .map(([value, data]) => {
                const action = frappe.unscrub(value);
                return `<div>
                            <h5>${action}</h5>
                            </br>
                            <a href="#" class="action-summary" data-name="${action}-${data.count}">
                                <h4 class="text-center" style="color: ${data.color}; font-size: x-large;">
                                    ${data.count}
                                </h4>
                            </a>
                        </div>`;
            })
            .join("");

        const action_performed_html = `
            <div class="action-performed-summary mt-3 mb-3 w-100 d-flex justify-content-around align-items-center" style="border-bottom: 1px solid var(--border-color);">
                ${action_performed_cards}
            </div>
       `;

        let element = $('[data-fieldname="data_section"]');
        element.prepend(action_performed_html);

        const me = this;
        this.frm.$wrapper.find(".action-summary").click(async function (e) {
            const [action, action_count] = $(this).attr("data-name").split("-");

            if (action_count === "0") return;

            const fg = me.filter_group;
            const filter = [DOCTYPE, "ims_action", "=", action];

            if (fg.filter_exists(filter.slice(0, 2)) && !fg.filter_exists(filter))
                await me.filter_group.remove_filter([DOCTYPE, "ims_action"]);

            me.update_filter(e, "ims_action", action, me);
        });
    }

    get_bill_no_bill_date(row) {
        return `
            ${row.bill_no}
            <br/>
            ${frappe.datetime.str_to_user(row.bill_date) || ""}
        `;
    }

    process_data(data = this.frm.__invoice_data) {
        if (!data || !this.frm?.doc?.period) return;

        const { period } = this.frm.doc;
        const month = period.slice(0, 2);
        const year = period.slice(2);
        const reference_date = new Date(year, month, 0);

        for (const row of data) {
            // Change match status of invoices in which supplier has uploaded invoices for next period and invoice is matched
            const bill_date = str_to_obj(row._inward_supply.bill_date);
            if (row._purchase_invoice?.name && bill_date > reference_date) {
                row.match_status = "Suggested Mark as Pending";
                continue;
            }

            // Change match status of invoices in which purchase is booked in next period
            // but supplier has filed return in current period
            if (!row._purchase_invoice?.posting_date) continue;
            const posting_date = str_to_obj(row._purchase_invoice.posting_date);

            if (posting_date > reference_date) {
                row.match_status = "Suggested Mark as Pending";
            }
        }
    }
}

class IMSAction {
    RETRY_INTERVALS = [2000, 3000, 15000, 30000, 60000, 120000, 300000, 600000, 720000]; // 5 second, 15 second, 30 second, 1 min, 2 min, 5 min, 10 min, 12 min

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
        if (!this.frm.doc.data_state) {
            this.frm.page.set_primary_action(__("Show Invoices"), () =>
                this.get_ims_data()
            );
        } else {
            this.frm.page.set_primary_action(__("Upload Invoices"), () =>
                this.upload_ims_data()
            );
        }

        // Download Button
        this.frm.add_custom_button(__("Download Invoices"), () => {
            render_empty_state(this.frm);
            this.download_ims_data();
        });

        // Export button
        this.frm.add_custom_button(__("Export"), () => this.export_data());
    }

    setup_row_actions() {
        // Setup Custom Buttons
        if (!this.frm.reconciliation_tabs?.data?.length) return;
        if (this.frm.get_active_tab()?.df.fieldname == "invoice_tab") {
            this.frm.add_custom_button(
                __("Unlink"),
                () => reconciliation.unlink_documents(this.frm),
                __("Actions")
            );
            this.frm.add_custom_button(__("dropdown-divider"), () => {}, __("Actions"));
        }

        // Setup Bulk Actions
        ["No Action", "Accept", "Pending", "Reject"].forEach(action =>
            this.frm.add_custom_button(
                __(action),
                () => apply_bulk_action(this.frm, ACTION_MAP[action]),
                __("Actions")
            )
        );

        // Add Dropdown Divider to differentiate between IMS and Reconciliation Actions
        this.frm.$wrapper
            .find("[data-label='dropdown-divider']")
            .addClass("dropdown-divider");

        // move actions button next to filters
        for (let button of this.frm.$wrapper.find(
            ".custom-actions .inner-group-button"
        )) {
            if (button.innerText?.trim() != __("Actions")) continue;
            this.frm.$wrapper.find(".custom-button-group .inner-group-button").remove();
            $(button).appendTo(this.frm.$wrapper.find(".custom-button-group"));
        }
    }

    async download_ims_data() {
        await taxpayer_api.call({
            method: `${DOC_PATH}.download_invoices`,
            args: { company_gstin: this.frm.doc.company_gstin },
        });

        frappe.show_alert({
            message: __("Downloading Invoices"),
        });
    }

    async get_ims_data() {
        const { message } = await this.frm.call("autoreconcile_and_get_data");
        this.frm.__invoice_data = message.invoice_data;

        this.frm.reconciliation_tabs.render_data(this.frm.__invoice_data);
        this.frm.doc.data_state = this.frm.__invoice_data.length
            ? "available"
            : "unavailable";

        if (message.pending_actions.length) {
            this.handle_upload_status();
        }

        // Toggle HTML fields
        this.frm.refresh();
    }

    async upload_ims_data() {
        if (!this.filter_invoices_to_upload().length) {
            frappe.msgprint({
                title: __("No Data Found"),
                message: __("No Invoices to Upload"),
                indicator: "red",
            });
            return;
        }

        frappe.show_alert(__("Checking Upload Status"));

        const save_status = await this.upload_and_check_status("save");
        const reset_status = await this.upload_and_check_status("reset");

        this.handle_upload_status(save_status, reset_status);
    }

    async upload_and_check_status(action) {
        await taxpayer_api.call({
            method: `${DOC_PATH}.${action}_invoices`,
            args: { company_gstin: this.frm.doc.company_gstin },
        });

        return this.get_upload_status_with_retry(action);
    }

    async handle_upload_status(save_status, reset_status) {
        if (!save_status) save_status = await this.get_upload_status_with_retry("save");

        if (!reset_status)
            reset_status = await this.get_upload_status_with_retry("reset");

        const error_statuses = ["ER", "PE"];
        if (
            error_statuses.includes(save_status.status_cd) ||
            error_statuses.includes(reset_status.status_cd)
        )
            return this.on_failed_upload();

        return this.on_successful_upload();
    }

    get_upload_status_with_retry(action, retries = 0, now = false) {
        return new Promise(resolve => {
            setTimeout(
                async () => {
                    const { message } = await taxpayer_api.call({
                        method: `${DOC_PATH}.check_action_status`,
                        args: { company_gstin: this.frm.doc.company_gstin, action },
                    });

                    if (!message.status_cd) {
                        resolve({ status_cd: "ER" });
                        return;
                    }

                    if (
                        message.status_cd === "IP" &&
                        retries < this.RETRY_INTERVALS.length
                    ) {
                        resolve(
                            await this.get_upload_status_with_retry(action, retries + 1)
                        );
                        return;
                    }

                    // Not IP
                    resolve(message);
                },
                now ? 0 : this.RETRY_INTERVALS[retries]
            );
        });
    }

    filter_invoices_to_upload() {
        return this.frm.reconciliation_tabs.data.filter(row => row.pending_upload);
    }

    on_failed_upload() {
        frappe.msgprint({
            message:
                "An error occurred while uploading the data. Please try downloading the data again and re-uploading it.",
            indicator: "red",
            title: __("GSTN Sync Required"),
            primary_action: {
                label: __("Sync and Reupload"),
                action: () => {
                    frappe.hide_msgprint();
                    render_empty_state(this.frm);

                    taxpayer_api.call({
                        method: `${DOC_PATH}.sync_with_gstn_and_reupload`,
                        args: { company_gstin: this.frm.doc.company_gstin },
                    });
                },
            },
        });
    }

    on_successful_upload() {
        // refresh existing data
        const data = this.frm.reconciliation_tabs.data;
        data.forEach(row => {
            if (!row.pending_upload) return;

            row.pending_upload = false;
            row.previous_ims_action = row.ims_action;
        });

        this.frm.reconciliation_tabs.refresh(data);

        frappe.show_alert({
            message: __("Uploaded Invoices Successfully"),
            indicator: "green",
        });
    }

    async export_data() {
        if (!this.frm.reconciliation_tabs.filtered_data) {
            await this.frm.ims_actions.get_ims_data();
        }

        const url = `${DOC_PATH}.download_excel_report`;
        open_url_post(`/api/method/${url}`, {
            data: JSON.stringify(this.frm.reconciliation_tabs.filtered_data),
            doc: JSON.stringify({
                company: this.frm.doc.company,
                company_gstin: this.frm.doc.company_gstin,
            }),
        });
    }
}

class DetailViewDialog extends reconciliation.detail_view_dialog {
    _get_custom_actions() {
        // setup actions
        let actions = ["No Action", "Reject"].filter(
            action => ACTION_MAP[action] != this.row.ims_action
        );

        if (
            this.row.match_status !== "Missing in PI" &&
            this.row.ims_action != "Accepted"
        )
            actions.push("Accept");

        if (this.row.is_pending_action_allowed && this.row.ims_action != "Pending")
            actions.push("Pending");

        if (this.row.match_status == "Missing in PI") actions.push("Create", "Link");
        else actions.push("Unlink");

        return actions;
    }

    _apply_custom_action(action) {
        if (action == "Unlink") {
            reconciliation.unlink_documents(this.frm, [this.row]);
        } else if (action == "Link") {
            reconciliation.link_documents(
                this.frm,
                this.data.purchase_invoice_name,
                this.data.inward_supply_name,
                this.dialog.get_value("doctype"),
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
            apply_action(this.frm, ACTION_MAP[action], [this.row.inward_supply_name]);
        }
    }

    _get_button_css(action) {
        if (action == "No Action") return "btn-secondary";
        if (action == "Accept") return "btn-success not-grey";
        if (action == "Reject") return "btn-danger not-grey";
        if (action == "Pending") return "btn-warning not-grey";
        if (action == "Create") return "btn-primary not-grey";
        if (action == "Link") return "btn-primary not-grey btn-link disabled";
    }

    _set_missing_doctype() {
        if (this.row.match_status == "Missing in PI")
            this.missing_doctype = "Purchase Invoice";
        else return;

        this.doctype_options = ["Purchase Invoice"];
    }
}

function render_empty_state(frm) {
    frm.__invoice_data = null;
    frm.doc.data_state = null;

    $(".action-performed-summary").remove();

    frm.refresh();
}

function apply_bulk_action(frm, action) {
    const active_tab = frm.get_active_tab()?.df.fieldname;
    if (!active_tab) return;

    const tab = frm.reconciliation_tabs.tabs[active_tab];

    // from current tab
    const selected_rows = tab.datatable.get_checked_items();
    if (!selected_rows.length) {
        frappe.show_alert({ message: __("Please select invoices"), indicator: "red" });
        return;
    }

    // summary => invoice
    const affected_rows = get_affected_rows(
        active_tab,
        selected_rows,
        frm.reconciliation_tabs.filtered_data
    );

    apply_action(frm, action, affected_rows);

    if (tab) tab.datatable.clear_checked_items();
}

async function apply_action(frm, action, invoice_names) {
    // Validate and Update JS
    let pending_not_allowed = [];
    let accept_not_allowed = [];
    let supplier_return_not_filed = [];
    let new_data = [];

    frm.reconciliation_tabs.data.forEach(row => {
        if (invoice_names.includes(row.inward_supply_name)) {
            if (action === "Accepted" && !row.is_supplier_return_filed) {
                supplier_return_not_filed.push(row.inward_supply_name);
            }
            if (!is_pending_allowed(row, action)) {
                pending_not_allowed.push(row.inward_supply_name);
            } else if (!is_accept_allowed(row, action)) {
                accept_not_allowed.push(row.inward_supply_name);
            } else {
                row.ims_action = action;

                // Update pending upload status
                if (row.ims_action !== row.previous_ims_action)
                    row.pending_upload = true;
                else row.pending_upload = false;
            }
        }

        new_data.push({ ...row });
    });

    invoice_names = invoice_names.filter(
        name =>
            !(pending_not_allowed.includes(name) || accept_not_allowed.includes(name))
    );

    if (pending_not_allowed.length) {
        frappe.msgprint({
            message: __(
                "Some invoices are not allowed to be marked as <strong>Pending</strong>."
            ),
            indicator: "red",
        });
    } else if (accept_not_allowed.length) {
        frappe.msgprint({
            message: __(
                "Some invoices cannot be <strong>Accepted</strong>. Please ensure they are linked to a purchase."
            ),
            indicator: "red",
        });
    }

    if (!invoice_names.length) return;

    // If in some invoices "Accept" action is allowed and Supplier has Not Filed Return
    if (supplier_return_not_filed.length) {
        frappe.show_alert(
            {
                message: __(
                    "Some invoices are <strong>Accepted</strong> where the Supplier has not filed the return"
                ),
                indicator: "orange",
            },
            10
        );
    }

    // Update
    frm._call("update_action", { invoice_names, action });

    frm.reconciliation_tabs.refresh(new_data);
    frappe.show_alert({ message: "Action applied successfully", indicator: "green" });
}

function is_pending_allowed(row, action) {
    if (action === "Pending" && !row.is_pending_action_allowed) return false;
    return true;
}

function is_accept_allowed(row, action) {
    // "Accept" not allowed where Purchase is not linked
    if (action === "Accepted" && row.match_status === "Missing in PI") return false;
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

    if (tab == "match_summary_tab")
        invoices = data.filter(
            inv => selection.filter(row => row.match_status == inv.match_status).length
        );

    if (tab == "action_summary_tab")
        invoices = data.filter(
            inv =>
                selection.filter(row => category_map[row.category] == inv.doc_type)
                    .length
        );

    return invoices.map(row => row.inward_supply_name);
}

function show_download_invoices_message(frm) {
    if (!api_enabled) return;

    const msg_tag = frm
        .get_field("no_invoice_data")
        .$wrapper.find("#download-invoices-alert");

    // show alert
    msg_tag.removeClass("hidden");

    // setup listener
    msg_tag.on("click", () => {
        frm.ims_actions.download_ims_data();
    });
}

async function set_period_options(frm) {
    if (!(frm.doc.company && frm.doc.company_gstin)) return;

    const { message: period_options } = await frappe.call({
        method: "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.get_period_options",
        args: { company: frm.doc.company, company_gstin: frm.doc.company_gstin },
    });

    frm.get_field("period").set_data(period_options);
    frm.set_value("period", period_options[0]);
}

function str_to_obj(d) {
    return frappe.datetime.user_to_obj(frappe.datetime.str_to_user(d));
}
