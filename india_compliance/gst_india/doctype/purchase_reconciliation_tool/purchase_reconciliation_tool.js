// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

// TODO: change the namespace
// TODO: replace the demo data
frappe.provide("reco_tool");

const tooltip_info = {
    purchase_period: "Returns purchases during this period where no match is found.",
    inward_supply_period:
        "Returns all documents from GSTR 2A/2B during this return period.",
};

const api_enabled = ic.is_api_enabled();

const ReturnType = {
    GSTR2A: "GSTR2a",
    GSTR2B: "GSTR2b",
};

frappe.ui.form.on("Purchase Reconciliation Tool", {
    async setup(frm) {
        ic.setup_tooltip(frm, tooltip_info);

        await frappe.require("purchase_reco_tool.bundle.js");
        frm.purchase_reconciliation_tool = new PurchaseReconciliationTool(frm);
    },

    async company(frm) {
        if (frm.doc.company) {
            const options = await set_gstin_options(frm);
            frm.set_value("company_gstin", options[0]);
        }
    },

    refresh(frm) {
        fetch_date_range(frm, "purchase");
        fetch_date_range(frm, "inward_supply");

        api_enabled
            ? frm.add_custom_button("Download", () => show_gstr_dialog(frm))
            : frm.add_custom_button("Upload", () => show_gstr_dialog(frm, false));

        // if (frm.doc.company) set_gstin_options(frm);
    },

    purchase_period(frm) {
        fetch_date_range(frm, "purchase");
    },

    inward_supply_period(frm) {
        fetch_date_range(frm, "inward_supply");
    },

    after_save(frm) {
        frm.purchase_reconciliation_tool.refresh(frm);
    },
});

class PurchaseReconciliationTool {
    constructor(frm) {
        this.frm = frm;
        this.data = frm.doc.__onload?.reconciliation_data?.data;
        this.render_tab_group();
        this.render_data_tables();
    }

    refresh(frm) {
        this.frm = frm;
        this.data = frm.doc.__onload?.reconciliation_data?.data;
        this.tabs.invoice_tab.data_table_manager.datatable.refresh(
            this.get_invoice_data()
        );
        this.tabs.supplier_tab.data_table_manager.datatable.refresh(
            this.get_supplier_data()
        );
        this.tabs.summary_tab.data_table_manager.datatable.refresh(
            this.get_summary_data()
        );
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
            body: this.frm.get_field("reconciliation_html").$wrapper,
            frm: this.frm,
        });

        this.tab_group.make();

        // make tabs_dict for easy access
        this.tabs = Object.fromEntries(
            this.tab_group.tabs.map(tab => [tab.df.fieldname, tab])
        );
    }

    render_data_tables() {
        this.tabs.summary_tab.data_table_manager = new ic.DataTableManager({
            $wrapper: this.tab_group.get_field("summary_data").$wrapper,
            columns: this.get_summary_columns(),
            data: this.get_summary_data(),
            options: {
                cellHeight: 55,
            },
        });

        this.tabs.supplier_tab.data_table_manager = new ic.DataTableManager({
            $wrapper: this.tab_group.get_field("supplier_data").$wrapper,
            columns: this.get_supplier_columns(),
            options: {
                cellHeight: 55,
            },
            data: this.get_supplier_data(),
        });
        this.tabs.invoice_tab.data_table_manager = new ic.DataTableManager({
            $wrapper: this.tab_group.get_field("invoice_data").$wrapper,
            columns: this.get_invoice_columns(),
            options: {
                cellHeight: 55,
            },
            data: this.get_invoice_data(),
        });
    }

    get_summary_data() {
        const data = {};
        this.data?.forEach(row => {
            let new_row = data[row.isup_match_status];
            if (!new_row) {
                new_row = data[row.isup_match_status] = {
                    isup_match_status: row.isup_match_status,
                    count_isup_docs: 0,
                    count_pur_docs: 0,
                    count_action_taken: 0,
                    total_docs: 0,
                    tax_diff: 0,
                    taxable_value_diff: 0,
                };
            }
            if (row.isup_name) new_row.count_isup_docs += 1;
            if (row.name) new_row.count_pur_docs += 1;
            if (row.isup_action != "No Action") new_row.count_action_taken += 1;
            new_row.total_docs += 1;
            new_row.tax_diff += row.tax_diff || 0;
            new_row.taxable_value_diff += row.taxable_value_diff || 0;
        });
        return Object.values(data);
    }

    get_summary_columns() {
        return [
            {
                label: "Match Status",
                fieldname: "isup_match_status",
                width: 200,
            },
            {
                label: "Count <br>2A/2B Docs",
                fieldname: "count_isup_docs",
                width: 180,
                align: "center",
            },
            {
                label: "Count <br>Purchase Docs",
                fieldname: "count_pur_docs",
                width: 180,
                align: "center",
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_diff",
                width: 180,
                align: "center",
                format: (value, row, column, data) => {
                    return frappe.form.get_formatter(column.docfield.fieldtype)(
                        format_number(value),
                        column.docfield,
                        { always_show_decimals: true },
                        data
                    );
                },
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_diff",
                width: 200,
                align: "center",
                format: (value, row, column, data) => {
                    return frappe.form.get_formatter(column.docfield.fieldtype)(
                        format_number(value),
                        column.docfield,
                        { always_show_decimals: true },
                        data
                    );
                },
            },
            {
                label: "% Action Taken",
                fieldname: "action_taken",
                width: 180,
                align: "center",
                format: (value, row, column, data) => {
                    return frappe.form.get_formatter(column.docfield.fieldtype)(
                        roundNumber(
                            (data.count_action_taken / data.total_docs) * 100,
                            2
                        ) + " %",
                        column.docfield,
                        { always_show_decimals: true },
                        data
                    );
                },
            },
        ];
    }

    get_supplier_data() {
        const data = {};
        this.data?.forEach(row => {
            let new_row = data[row.supplier_gstin];
            if (!new_row) {
                new_row = data[row.supplier_gstin] = {
                    supplier_name: row.supplier_name,
                    supplier_gstin: row.supplier_gstin,
                    count_isup_docs: 0,
                    count_pur_docs: 0,
                    count_action_taken: 0,
                    total_docs: 0,
                    tax_diff: 0,
                    taxable_value_diff: 0,
                };
            }
            if (row.isup_name) new_row.count_isup_docs += 1;
            if (row.name) new_row.count_pur_docs += 1;
            if (row.isup_action != "No Action") new_row.count_action_taken += 1;
            new_row.total_docs += 1;
            new_row.tax_diff += row.tax_diff || 0;
            new_row.taxable_value_diff += row.taxable_value_diff || 0;
        });
        return Object.values(data);
    }

    get_supplier_columns() {
        return [
            {
                label: "Supplier",
                fieldname: "supplier",
                fieldtype: "Link",
                width: 200,
                _value: (value, column, data) => {
                    if (data && column.field === "supplier") {
                        column.docfield.link_onclick = `reco_tool.apply_filters(${JSON.stringify(
                            {
                                tab: "invoice_tab",
                                filters: {
                                    supplier_name: data.supplier_gstin,
                                },
                            }
                        )})`;
                    }

                    return `
                            ${data.supplier_name}
                            <br />
                            <span style="font-size: 0.9em">
                                ${data.supplier_gstin || ""}
                            </span>
                        `;
                },
                dropdown: false,
            },
            {
                label: "Count <br>2A/2B Docs",
                fieldname: "count_isup_docs",
                align: "center",
                width: 150,
            },
            {
                label: "Count <br>Purchase Docs",
                fieldname: "count_pur_docs",
                align: "center",
                width: 150,
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_diff",
                align: "center",
                width: 150,
                _value: (...args) => {
                    return format_number(args[0]);
                },
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_diff",
                align: "center",
                width: 180,
                _value: (...args) => {
                    return format_number(args[0]);
                },
            },
            {
                label: "% Action Taken",
                fieldname: "action_taken",
                align: "center",
                _value: (...args) => {
                    return (
                        roundNumber(
                            (args[2].count_action_taken / args[2].total_docs) * 100,
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
        return this.data;
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
                label: "Supplier",
                fieldname: "supplier_name",
                width: 200,
                _value: (...args) => {
                    return `${args[2].supplier_name}
                            <br />
                            <span style="font-size: 0.9em">
                                ${args[2].supplier_gstin || ""}
                            </span>`;
                },
                dropdown: false,
            },
            {
                label: "Bill No.",
                fieldname: "bill_no",
                width: 120,
            },
            {
                label: "Date",
                fieldname: "bill_date",
                width: 120,
            },
            {
                label: "Match Status",
                fieldname: "isup_match_status",
                width: 120,
            },
            {
                label: "Purchase Invoice",
                fieldname: "name",
                fieldtype: "Link",
                doctype: "Purchase Invoice",
                align: "center",
                width: 150,
            },
            {
                label: "Inward Supply",
                fieldname: "isup_name",
                fieldtype: "Link",
                doctype: "Inward Supply",
                align: "center",
                width: 150,
            },
            {
                label: "Tax Diff <br>2A/2B - Purchase",
                fieldname: "tax_diff",
                width: 150,
                align: "center",
                _value: (...args) => {
                    return format_number(args[0]);
                },
            },
            {
                fieldname: "taxable_value_diff",
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                width: 180,
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
                fieldname: "isup_action",
            },
        ];
    }
}

async function fetch_date_range(frm, field_prefix) {
    const from_date_field = field_prefix + "_from_date";
    const to_date_field = field_prefix + "_to_date";
    const period = frm.doc[field_prefix + "_period"];
    if (period == "Custom") return;

    const { message } = await frm.call("get_date_range", { period });
    if (!message) return;

    frm.set_value(from_date_field, message[0]);
    frm.set_value(to_date_field, message[1]);
}

function get_gstr_dialog_fields() {
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
        },
        {
            fieldtype: "Column Break",
        },
        {
            label: "Fiscal Year",
            fieldname: "fiscal_year",
            fieldtype: "Link",
            options: "Fiscal Year",
            default: frappe.defaults.get_default("fiscal_year"),
            get_query() {
                return {
                    filters: {
                        year_end_date: [">", "2017-06-30"],
                    },
                };
            },
        },
    ];
}

function get_history_fields(for_download = true) {
    const label = for_download ? "Download History" : "Upload History";

    return [
        { label, fieldtype: "Section Break" },
        { label, fieldname: "history", fieldtype: "HTML" },
    ];
}

function show_gstr_dialog(frm, for_download = true) {
    let dialog;
    if (for_download) {
        dialog = _show_download_gstr_dialog();
    } else {
        dialog = _show_upload_gstr_dialog();
        dialog.fields_dict.attach_file.df.onchange = () => {
            const attached_file = dialog.get_value("attach_file");
            if (!attached_file) return;
            fetch_return_period_from_file(frm, dialog);
        };
    }

    dialog.fields_dict.fiscal_year.df.onchange = () => {
        fetch_download_history(frm, dialog, for_download);
    };

    dialog.fields_dict.return_type.df.onchange = () => {
        set_dialog_actions(frm, dialog, for_download);
        fetch_download_history(frm, dialog, for_download);
    };

    set_dialog_actions(frm, dialog, for_download);
    fetch_download_history(frm, dialog, for_download);
}

function set_dialog_actions(frm, dialog, for_download) {
    const return_type = dialog.get_value("return_type");

    if (for_download) {
        if (return_type === ReturnType.GSTR2A) {
            dialog.set_primary_action(__("Download All"), () => {
                download_gstr(
                    frm,
                    dialog.get_value("return_type"),
                    dialog.get_value("fiscal_year"),
                    false
                );
                dialog.hide();
            });
            dialog.set_secondary_action_label(__("Download Missing"));
            dialog.set_secondary_action(() => {
                download_gstr(
                    frm,
                    dialog.get_value("return_type"),
                    dialog.get_value("fiscal_year"),
                    true
                );
                dialog.hide();
            });
        } else if (return_type === ReturnType.GSTR2B) {
            dialog.set_primary_action(__("Download"), () => {
                download_gstr(
                    frm,
                    dialog.get_value("return_type"),
                    dialog.get_value("fiscal_year"),
                    true
                );
                dialog.hide();
            });
            dialog.set_secondary_action_label(null);
            dialog.set_secondary_action(null);
        }
    } else {
        dialog.set_primary_action(__("Upload"), () => {
            const file_path = dialog.get_value("attach_file");
            const period = dialog.get_value("period");
            if (!file_path) frappe.throw(__("Please select a file first!"));
            if (!period)
                frappe.throw(
                    __(
                        "Could not fetch period from file, make sure you have selected the correct file!"
                    )
                );
            upload_gstr(frm, return_type, period, file_path);
            dialog.hide();
        });
    }
}

function _show_download_gstr_dialog() {
    const dialog = new frappe.ui.Dialog({
        title: __("Download Data from GSTN"),
        fields: [...get_gstr_dialog_fields(), ...get_history_fields()],
    });
    return dialog.show();
}

function _show_upload_gstr_dialog() {
    const dialog = new frappe.ui.Dialog({
        title: __("Upload Data"),
        fields: [
            ...get_gstr_dialog_fields(),
            {
                label: "Period",
                fieldname: "period",
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
            },
            ...get_history_fields(false),
        ],
    });
    return dialog.show();
}

async function fetch_download_history(frm, dialog, for_download = true) {
    const { message } = await frm.call("get_import_history", {
        return_type: dialog.get_value("return_type"),
        fiscal_year: dialog.get_value("fiscal_year"),
        for_download: for_download,
    });

    if (!message) return;
    dialog.fields_dict.history.set_value(message);
}

async function fetch_return_period_from_file(frm, dialog) {
    const return_type = dialog.get_value("return_type");
    const file_path = dialog.get_value("attach_file");
    const { message } = await frm.call("get_return_period_from_file", {
        return_type,
        file_path,
    });

    if (!message) {
        dialog.get_field("attach_file").clear_attachment();
        frappe.throw(
            __(
                "Please make sure you have uploaded the correct file. File Uploaded is not for {0}",
                [return_type]
            )
        );

        return dialog.hide();
    }

    await dialog.set_value("period", message);
    dialog.refresh();
}

async function download_gstr(
    frm,
    return_type,
    fiscal_year,
    only_missing = true,
    otp = null
) {
    let method;
    const args = { fiscal_year, otp };
    if (return_type === ReturnType.GSTR2A) {
        method = "download_gstr_2a";
        args.force = !only_missing;
    } else {
        method = "download_gstr_2b";
    }

    reco_tool.show_progress(frm, "download");
    const { message } = await frm.call(method, args);
    if (message && message.errorCode == "RETOTPREQUEST") {
        const otp = await get_gstin_otp();
        if (otp) download_gstr(frm, return_type, fiscal_year, only_missing, otp);
        return;
    }
}

function get_gstin_otp() {
    return new Promise(resolve => {
        frappe.prompt(
            {
                fieldtype: "Data",
                label: "One Time Password",
                fieldname: "otp",
                reqd: 1,
                description:
                    "An OTP has been sent to your registered mobile/email for further authentication. Please provide OTP.",
            },
            function ({ otp }) {
                resolve(otp);
            },
            "Enter OTP"
        );
    });
}

function upload_gstr(frm, return_type, period, file_path) {
    reco_tool.show_progress(frm, "upload");
    frm.call("upload_gstr", { return_type, period, file_path });
}

// TODO: refactor progress
reco_tool.show_progress = function (frm, type) {
    if (type == "download") {
        frappe.run_serially([
            () => update_progress(frm, "update_api_progress"),
            () => update_progress(frm, "update_transactions_progress"),
        ]);
    } else if (type == "upload") {
        update_progress(frm, "update_transactions_progress");
    }
};

function update_progress(frm, method) {
    frappe.realtime.on(method, data => {
        const { current_progress } = data;
        const message =
            method == "update_api_progress"
                ? __("Fetching data from GSTN")
                : __("Updating Inward Supply for Return Period {0}", [
                      data.return_period,
                  ]);

        frm.dashboard.show_progress("Import GSTR Progress", current_progress, message);
        frm.page.set_indicator(__("In Progress"), "orange");
        if (data.is_last_period) {
            frm.flag_last_return_period = data.return_period;
        }
        if (
            current_progress == 100 &&
            method != "update_api_progress" &&
            frm.flag_last_return_period == data.return_period
        ) {
            setTimeout(() => {
                frm.dashboard.hide();
                frm.refresh();
                frm.page.set_indicator(__("Success"), "green");
                frm.dashboard.set_headline("Successfully Imported");
                setTimeout(() => {
                    frm.page.clear_headline();
                }, 2000);
                frm.save();
            }, 1000);
        }
    });
}

reco_tool.apply_filters = function ({ tab, filters }) {
    if (!cur_frm) return;

    // Switch to the tab
    const { tabs } = cur_frm.purchase_reconciliation_tool;
    tab = tabs && (tabs[tab] || Object.values(tabs).find(tab => tab.is_active()));
    tab.set_active();

    // apply filters
    const _filters = {};
    for (const [fieldname, filter] of Object.entries(filters)) {
        const column = tab.data_table_manager.get_column(fieldname);
        column.$filter_input.value = filter;
        _filters[column.colIndex] = filter;
    }

    tab.data_table_manager.datatable.columnmanager.applyFilter(_filters);
};

function get_icon(value, column, data, icon) {
    /**
     * Returns custom ormated value for the row.
     * @param {string} value        Current value of the row.
     * @param {object} column       All properties of current column
     * @param {object} data         All values in its core form for current row
     * @param {string} icon         Return icon (font-awesome) as the content
     */

    return `<button class="btn" title="hello">
                <i class="fa fa-${icon}"></i>
            </button>`;
}
