// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

const api_enabled = india_compliance.is_api_enabled();
const DOCTYPE = "GST Invoice Management System";

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
    Link: "Link",
    Create: "Create",
    Unlink: "Unlink",
};

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        await frappe.require("ims.bundle.js");

        frm.ims = new IMS(frm);

        frm.trigger("company");

        // Setup Listeners

        // Download Queued
        frappe.realtime.on("ims_download_queued", message => {
            frappe.msgprint(message["message"]);
        });

        // Downloaded and Reconciled Invoices
        frappe.realtime.on("ims_download_completed", message => {
            this.ims_actions.get_ims_data(frm);
            frappe.show_alert({
                message: message["message"],
                indicator: "green",
            });
        });

        // Check Upload Status
        frappe.realtime.on("check_ims_upload_status", message => {
            this.ims_actions.handle_upload_and_reset_request();
        });
    },

    async company(frm) {
        render_empty_state(frm);
        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm);

        frm.set_value("company_gstin", options[0]);
    },

    company_gstin: render_empty_state,

    refresh(frm) {
        show_download_invoices_message(frm);

        this.ims_actions = new IMSAction(frm);
        this.ims_actions.setup_primary_actions();
        this.ims_actions.setup_custom_buttons();
    },
});

class IMS extends india_compliance.summary_view {
    RETRY_INTERVALS = [2000, 3000, 15000, 30000, 60000, 120000, 300000, 600000, 720000]; // 5 second, 15 second, 30 second, 1 min, 2 min, 5 min, 10 min, 12 min

    constructor(frm) {
        super(frm, DOCTYPE);
    }

    init(frm) {
        super.init(frm, ["invoice", "match_summary", "action_summary"]);
        this.$wrapper = this.frm.get_field("invoice_html").$wrapper;
    }

    generate_data() {
        super.generate_data("__invoice_data");
    }

    refresh(data) {
        super.refresh(data);
        this.set_actions_summary();
    }

    render_tab_group() {
        const fields = [
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

        super.render_tab_group(fields);
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
                options: ["No Action", "Accepted", "Rejected", "Pending"],
            },
            {
                label: "Document Type",
                fieldname: "doc_type",
                fieldtype: "Select",
                options: ["Invoice", "Credit Note", "Debit Note"],
            },
            {
                label: "Pending Upload",
                fieldname: "pending_upload",
                fieldtype: "Check",
            },
            {
                label: "Classification",
                fieldname: "classification",
                fieldtype: "Select",
                options: ["B2B", "B2BA", "CDNR", "CDNRA"],
            },
        ];

        fields.forEach(field => (field.parent = DOCTYPE));
        return fields;
    }

    set_listeners() {
        const me = this;

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
            if (row.action != "No Action") new_row.action_taken_count += 1;
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
                fieldname: "bill_no",
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
                bill_no: row.bill_no,
                classification: row._inward_supply.classification,
                ims_action: row.ims_action || "",
                match_status: row.match_status,
                linked_doc: row.purchase_invoice_name,
                tax_difference: row.tax_difference,
                taxable_value_difference: row.taxable_value_difference,
                inward_supply_name: row.inward_supply_name,
                pending_upload: row.pending_upload,
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

    check_action_status_with_retry(action, retries = 0, now = false) {
        return new Promise(resolve => {
            setTimeout(
                async () => {
                    const { message } = await taxpayer_api.call({
                        method: "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.check_action_status",
                        args: {
                            company_gstin: this.frm.doc.company_gstin,
                            action,
                        },
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
                            await this.check_action_status_with_retry(
                                action,
                                retries + 1
                            )
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
            <div class="action-performed-summary m-3 d-flex justify-content-around align-items-center" style="border-bottom: 1px solid var(--border-color);">
                ${action_performed_cards}
            </div>
       `;

        let element = $('[data-fieldname="data_section"]');
        element.prepend(action_performed_html);

        const me = this;
        this.frm.$wrapper.find(".action-summary").click(function (e) {
            const [action, action_count] = $(this).attr("data-name").split("-");

            if (action_count === "0") return;
            me.update_filter(e, "ims_action", action, me);
        });
    }
}

class IMSAction {
    constructor(frm) {
        this.frm = frm;
    }

    setup_primary_actions() {
        // Primary Action
        this.frm.disable_save();
        if (!this.frm.doc.data_state) {
            this.frm.page.set_primary_action(__("Show Invoices"), () =>
                this.get_ims_data(this.frm)
            );
        } else {
            this.frm.page.set_primary_action(__("Upload Invoices"), () =>
                this.upload_ims_data(this.frm)
            );
        }

        this.frm.add_custom_button(__("Download Invoices"), async () => {
            render_empty_state(this.frm);
            await this.download_ims_data(this.frm);
        });
    }

    setup_custom_buttons() {
        // Setup Custom Buttons
        if (!this.frm.ims?.data?.length) return;
        if (this.frm.get_active_tab()?.df.fieldname == "invoice_tab") {
            this.frm.add_custom_button(
                __("Unlink"),
                () => reconciliation.unlink_documents(this.frm, this.frm.ims),
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

    async get_ims_data(frm) {
        const { message } = await frm.call("autoreconcile_and_get_data");
        frm.__invoice_data = message;

        frm.ims.generate_data();
        frm.doc.data_state = message.length ? "available" : "unavailable";

        // Toggle HTML fields
        frm.refresh();
    }

    async upload_ims_data(frm) {
        await taxpayer_api.call({
            method: "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.upload_invoices",
            args: {
                company_gstin: frm.doc.company_gstin,
            },
            callback: async r => {
                if (!r.message) {
                    frappe.msgprint({
                        title: __("No Data Found"),
                        message: __("No Invoices to Upload"),
                        indicator: "red",
                    });
                    return;
                }
                frappe.show_alert(__("Checking Upload Status"));

                this.handle_upload_and_reset_request();
            },
        });
    }

    async handle_upload_and_reset_request() {
        const upload_status = await this.frm.ims.check_action_status_with_retry(
            "upload"
        );
        const reset_status = await this.frm.ims.check_action_status_with_retry("reset");

        const error_statuses = ["ER", "PE"];
        if (
            error_statuses.includes(upload_status.status_cd) ||
            error_statuses.includes(reset_status.status_cd)
        ) {
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
                            method: "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.sync_with_gstn_and_reupload",
                            args: {
                                company_gstin: this.frm.doc.company_gstin,
                            },
                        });
                    },
                },
            });
            return;
        }

        frappe.show_alert({
            message: __("Uploaded Invoices Successfully"),
            indicator: "green",
        });
    }

    async download_ims_data(frm) {
        await taxpayer_api.call({
            method: "india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system.download_invoices",
            args: {
                company_gstin: frm.doc.company_gstin,
            },
        });

        frappe.show_alert({
            message: __("Downloading Invoices"),
        });
    }
}

class DetailViewDialog extends india_compliance.detail_view_dialog {
    async get_invoice_details() {
        const { message } = await this.frm._call("get_invoice_comparison", {
            purchase_name: this.row.purchase_invoice_name,
            inward_supply_name: this.row.inward_supply_name,
        });

        this.data = message;
    }

    _set_missing_doctype() {
        if (this.row.match_status == "Missing in PI")
            this.missing_doctype = "Purchase Invoice";
        else return;

        this.doctype_options = ["Purchase Invoice"];
    }

    async set_link_options() {
        super.set_link_options("get_purchase_invoice_options");
    }

    setup_actions() {
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

        super.setup_actions(actions);
    }

    _apply_custom_action(action) {
        super._apply_custom_action(
            this.frm.ims,
            ACTION_MAP[action],
            this.row.inward_supply_name,
            apply_action
        );
    }

    _get_button_css(action) {
        if (action == "No Action") return "btn-secondary";
        if (action == "Accept") return "btn-success not-grey";
        if (action == "Reject") return "btn-danger not-grey";
        if (action == "Pending") return "btn-warning not-grey";
        if (action == "Create") return "btn-primary not-grey";
        if (action == "Link") return "btn-primary not-grey btn-link disabled";
    }

    render_table() {
        super.render_table("invoice_detail_comparison");
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

    const tab = frm.ims.tabs[active_tab];

    // from current tab
    const selected_rows = tab.datatable.get_checked_items();
    if (!selected_rows.length)
        return frappe.show_alert({
            message: __("Please select invoices"),
            indicator: "red",
        });

    // summary => invoice
    const affected_rows = get_affected_rows(
        active_tab,
        selected_rows,
        frm.ims.filtered_data
    );

    apply_action(frm, action, affected_rows);

    if (tab) tab.datatable.clear_checked_items();
}

async function apply_action(frm, action, invoice_names) {
    // Validate and Update JS
    let pending_not_allowed = [];
    let accept_not_allowed = [];
    let new_data = [];
    frm.ims.data.forEach(row => {
        if (invoice_names.includes(row.inward_supply_name)) {
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

    // TODO: Better UX? Invoices details where such actions are not performed
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

    // Update
    frm._call("update_action", { invoice_names, action });

    frm.ims.refresh(new_data);
    frappe.show_alert({ message: "Action applied successfully", indicator: "green" });
}

function is_pending_allowed(row, action) {
    if (action === "Pending" && !row.is_pending_action_allowed) return false;
    return true;
}

function is_accept_allowed(row, action) {
    // "Accept" not allowed for Missing in PI
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

    if (tab == "summary_tab")
        invoices = data.filter(
            inv => selection.filter(row => row.match_status == inv.match_status).length
        );

    if (tab == "action_tab")
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
        this.ims_actions.download_ims_data(frm);
    });
}
