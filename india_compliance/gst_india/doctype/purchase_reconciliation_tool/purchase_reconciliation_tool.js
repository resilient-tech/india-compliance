// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt
frappe.provide("reco_tool");

const ReturnType = {
    GSTR2A: "GSTR2a",
    GSTR2B: "GSTR2b",
};

frappe.ui.form.on("Purchase Reconciliation Tool", {
    refresh(frm) {
        fetch_date_range(frm, "purchase");
        fetch_date_range(frm, "inward_supply");

        frm.add_custom_button(
            "GSTR 2A",
            () => show_gstr_dialog(frm, ReturnType.GSTR2A),
            "Download"
        );
        frm.add_custom_button(
            "GSTR 2B",
            () => show_gstr_dialog(frm, ReturnType.GSTR2B),
            "Download"
        );
        frm.add_custom_button(
            "GSTR 2A",
            () => show_gstr_dialog(frm, ReturnType.GSTR2A, false),
            "Upload"
        );
        frm.add_custom_button(
            "GSTR 2B",
            () => show_gstr_dialog(frm, ReturnType.GSTR2B, false),
            "Upload"
        );
    },

    purchase_period(frm) {
        fetch_date_range(frm, "purchase");
    },

    inward_supply_period(frm) {
        fetch_date_range(frm, "inward_supply");
    },
});

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

function get_dialog_fields(return_type) {
    return [
        {
            label: "GST Return Type",
            fieldname: "return_type",
            fieldtype: "Select",
            // read_only: 1,
            options: [
                { label: "GSTR 2A", value: ReturnType.GSTR2A },
                { label: "GSTR 2B", value: ReturnType.GSTR2B },
            ],
            default: return_type,
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

function show_gstr_dialog(frm, return_type, for_download = true) {
    let dialog;
    if (for_download) {
        dialog = _show_download_gstr_dialog(return_type);
    } else {
        dialog = _show_upload_gstr_dialog(return_type);
        dialog.fields_dict.fiscal_year.df.onchange = () => {
            const attached_file = dialog.get_value("attach_file");
            if (!attached_file) return;
            fetch_return_period_from_file(frm, dialog);
        };
    }

    dialog.fields_dict.fiscal_year.df.onchange = () => {
        fetch_download_history(frm, dialog, for_download);
    };

    dialog.fields_dict.return_type.df.onchange = () => {
        set_dialog_actions(dialog, dialog.get_value("return_type"));
        fetch_download_history(frm, dialog, for_download);
    };

    fetch_download_history(frm, dialog, for_download);
}

function set_dialog_actions(dialog, return_type) {
    if (return_type === ReturnType.GSTR2A) {
        dialog.set_primary_action(__("Download All"), () => {
            // TODO
        });
        dialog.set_secondary_action_label(__("Download Missing"));
        dialog.set_secondary_action(() => {
            // TODO
        });
    } else if (return_type === ReturnType.GSTR2B) {
        dialog.set_primary_action(__("Download"), () => {
            // TODO
        });
        dialog.set_secondary_action_label(null);
        dialog.set_secondary_action(null);
    }
}

function _show_download_gstr_dialog(return_type) {
    const dialog = new frappe.ui.Dialog({
        title: __("Download Data from GSTN"),
        fields: [...get_dialog_fields(return_type), ...get_history_fields()],
    });
    set_dialog_actions(dialog, return_type);
    return dialog.show();
}

function _show_upload_gstr_dialog(return_type) {
    const dialog = new frappe.ui.Dialog({
        title: __("Upload Data"),
        primary_action_label: __("Upload"),
        fields: [
            ...get_dialog_fields(return_type),
            {
                label: "Period",
                fieldname: "period",
                fieldtype: "Data",
                default: frappe.datetime.now_date(),
            },
            {
                fieldtype: "Section Break",
            },
            {
                label: "Attach File",
                fieldname: "attach_file",
                fieldtype: "Attach",
                description: "Attach .json file here",
                options: { restrictions: { allowed_file_types: ["json"] } },
            },
            ...get_history_fields(false),
        ],
    });

    if (return_type === ReturnType.GSTR2A) {
        dialog.primary_action = () => {
            // TODO: Upload Data
            dialog.hide();
        };
    } else {
        dialog.primary_action = () => {
            // TODO: Upload Data
            dialog.hide();
        };
    }

    return dialog.show();
}

async function fetch_download_history(frm, dialog, for_download = true) {
    const { message } = await frm.call("get_download_history", {
        return_type: dialog.get_value("return_type"),
        fiscal_year: dialog.get_value("fiscal_year"),
        for_download: for_download,
    });

    if (!message) return;
    dialog.fields_dict.history.set_value(message);
}

function download_gstr(frm, dialog, method, otp = null) {
    frm.call(method, {
        gstr_name: dialog.fields_dict.return_type.value,
        fiscal_year: dialog.fields_dict.fiscal_year.value,
        otp: otp,
    }).then(r => {
        if (r.message.errorCode == "RETOTPREQUEST") {
            reco_tool.get_gstin_otp(reco_tool.download_gstr, frm, dialog, method);
        }
    });
    let return_type = dialog.fields_dict.return_type.value;
    reco_tool.show_progress_gstr_2a_2b(frm, return_type, "download");
}

function upload_gstr(frm, dialog, method) {
    frm.call(method, {
        return_type: dialog.fields_dict.return_type.value,
        period: dialog.fields_dict.period.value,
        attach_file: dialog.fields_dict.attach_file.value,
    }).then(r => {
        console.log(r.message);
    });
    let return_type = dialog.fields_dict.return_type.value;
    reco_tool.show_progress_gstr_2a_2b(frm, return_type, "upload");
}

reco_tool.show_progress_gstr_2a_2b = function (frm, return_type, type) {
    if (type == "download") {
        frappe.run_serially([
            () =>
                create_or_update_progress(frm, return_type, "fetch_api_progress", type),
            () =>
                create_or_update_progress(
                    frm,
                    return_type,
                    return_type === "GSTR 2A"
                        ? "create_or_update_gstr_2a_progress"
                        : "create_or_update_b2b_progress",
                    type
                ),
            () =>
                create_or_update_progress(
                    frm,
                    return_type,
                    return_type == "GSTR 2B" ? "update_download_history_progress" : "",
                    type
                ),
        ]);
    } else if (type == "upload") {
        frappe.run_serially([
            () =>
                create_or_update_progress(
                    frm,
                    return_type,
                    return_type === "GSTR 2A"
                        ? "create_or_update_gstr_2a_progress"
                        : "create_or_update_b2b_progress",
                    type
                ),
            () =>
                create_or_update_progress(
                    frm,
                    return_type,
                    return_type == "GSTR 2B" ? "update_download_history_progress" : "",
                    type
                ),
        ]);
    }
};

function create_or_update_progress(frm, return_type, method, type) {
    frappe.realtime.on(method, data => {
        frm.import_in_progress = true;
        console.log(data);
        let percent, total, period;

        total = "total_b2b_data" in data ? data.total_b2b_data : data.total_ret_periods;

        period = type === "download" ? data.period : "";

        percent = Math.floor((data.current_idx * 100) / total);

        let message, msg;
        if (data.success) {
            let message_args = [data.current_idx, total, return_type, percent, period];

            msg =
                type == "upload"
                    ? __("Updating {2} transactions...", message_args)
                    : __("Downloading {2} records...", message_args);

            if (type == "download" && method == "fetch_api_progress") {
                message = __("Fetching {2} transactions...", message_args);
            } else if (method === "update_download_history_progress") {
                message = __(
                    "Update download history for {2} {0} of {1}, {3}% completed",
                    message_args
                );
            } else {
                message = msg;
            }
        }

        frm.dashboard.show_progress(__("Upload GSTR Progress"), percent, message);
        frm.page.set_indicator(__("In Progress"), "orange");
        if (data.current_idx === total) {
            setTimeout(() => {
                frm.dashboard.hide();
                frm.refresh();
                frm.dashboard.set_headline(
                    type == "upload"
                        ? "Successfully uploaded"
                        : "Successfully downloaded"
                );
            }, 2000);
            frm.page.set_indicator(__("Success"), "green");
        }
    });
}

async function fetch_return_period_from_file(frm, dialog) {
    const return_type = dialog.get_value("return_type");
    const file_path = dialog.get_value("attach_file");
    const { message } = await frm.call("get_return_period_from_file", {
        return_type,
        file_path,
    });

    if (!message) {
        frappe.throw(
            __(
                "Please make sure you have uploaded the correct file. File Uploaded is not for {0}",
                [return_type]
            )
        );

        return dialog.hide();
    }

    dialog.set_value("period", r.message);
}

const purchase_reco_data_manager = class DataTableManager {
    constructor(opts) {
        Object.assign(this, opts);
        this.make_dt();
    }

    make_dt() {
        var me = this;
        console.log(this.frm);
        if (this.$summary_dt) {
            var args = {
                company_gstin: this.frm.doc.company_gstin,
                purchase_from_date: this.frm.doc.purchase_from_date,
                purchase_to_date: this.frm.doc.purchase_to_date,
                inward_from_date: this.frm.doc.inward_supply_from_date,
                inward_to_date: this.frm.doc.inward_supply_to_date,
            };
            this.frm.call({
                method: "get_summary_data",
                args: args,
                callback: function (response) {
                    me.format_data(response.message);
                    me.get_dt_columns();
                    me.get_datatable();
                    me.set_listeners();
                },
            });
        } else if (this.$supplier_level_dt) {
            var method_to_call = "get_b2b_purchase";
            var args = {
                company_gstin: this.frm.doc.company_gstin,
                purchase_from_date: this.frm.doc.purchase_from_date,
                purchase_to_date: this.frm.doc.purchase_to_date,
            };
        } else if (this.$invoice_level_dt) {
            var method_to_call = "get_b2b_purchase";
            var args = {
                company_gstin: this.frm.doc.company_gstin,
                purchase_from_date: this.frm.doc.purchase_from_date,
                purchase_to_date: this.frm.doc.purchase_to_date,
            };
        }

        if (!this.$summary_dt) {
            this.frm.call(method_to_call, args).then(r => {
                if (!r.message) {
                    return;
                }
                console.log(r.message);
                me.format_data(r.message);
                me.get_dt_columns();
                me.get_datatable();
                me.set_listeners();
            });
        }
    }

    format_data(res_message) {
        this.transactions = [];
        var res_data = res_message;
        if (!Array.isArray(res_message)) {
            res_data = Object.values(res_message);
        }
        res_data.forEach(row => {
            console.log(row);
            this.transactions.push(this.format_row(row));
        });
    }

    format_row(row) {
        if (this.$summary_dt) {
            return [
                row["match_status"],
                row["no_of_inward_supp"],
                row["no_of_doc_purchase"],
                row["tax_diff"],
            ];
        }
        if (this.$supplier_level_dt) {
            return [
                row[0]["supplier_gstin"],
                row[0]["supplier_name"],
                row[0]["no_of_inward_supp"],
                row.length,
                row[0]["tax_diff"],
            ];
        }
        if (this.$invoice_level_dt) {
            return [
                row[0]["supplier_gstin"],
                row[0]["supplier_name"],
                row[0]["no_of_inward_supp"],
                row[0]["no_of_doc_purchase"],
                row[0]["tax_diff"],
            ];
        }
    }

    get_dt_columns() {
        if (this.$summary_dt) {
            this.columns = [
                {
                    name: "Match Type",
                    editable: false,
                    width: 100,
                },
                {
                    name: "No. of Doc Inward Supply",
                    editable: false,
                    width: 200,
                },
                {
                    name: "No. of Doc Purchase",
                    editable: false,
                    width: 200,
                },
                {
                    name: "Tax Diff",
                    editable: false,
                    width: 100,
                },
            ];
        }
        if (this.$supplier_level_dt) {
            this.columns = [
                {
                    name: "GSTIN",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Supplier Name",
                    editable: false,
                    width: 150,
                },
                {
                    name: "No. of Doc Inward Supply",
                    editable: false,
                    width: 200,
                },
                {
                    name: "No. of Doc Purchase",
                    editable: false,
                    width: 200,
                },
                {
                    name: "Tax Diff",
                    editable: false,
                    width: 100,
                },
            ];
        }
        if (this.$invoice_level_dt) {
            this.columns = [
                {
                    name: "GSTIN",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Supplier Name",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Inv No.",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Date",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Action Status",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Match Status",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Purchase Ref",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Inward Supp Ref",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Tax Diff",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Mismatch",
                    editable: false,
                    width: 100,
                },
                {
                    name: "Action",
                    editable: false,
                    width: 100,
                },
            ];
        }
    }

    get_datatable() {
        const datatable_options = {
            columns: this.columns,
            data: this.transactions,
            dynamicRowHeight: true,
            checkboxColumn: true,
            inlineFilters: true,
            events: {
                onCheckRow: () => {
                    const checked_items = this.get_checked_items();
                    this.toggle_actions_menu_button(checked_items.length > 0);
                },
            },
        };
        if (this.$summary_dt) {
            this.datatable = new frappe.DataTable(
                this.$summary_dt.fieldobj.$wrapper.get(0),
                datatable_options
            );

            $(`.${this.datatable.style.scopeClass} .dt-scrollable`).css({
                "max-height": "calc(500vh - 400px)",
                overflow: "auto visible",
            });

            if (this.transactions.length > 0) {
                console.log(this.datatable);
                this.$summary_dt.fieldobj.$wrapper.show();
            } else {
                this.$summary_dt.fieldobj.$wrapper.hide();
            }
        } else if (this.$supplier_level_dt) {
            this.datatable = new frappe.DataTable(
                this.$supplier_level_dt.fieldobj.$wrapper.get(0),
                datatable_options
            );

            $(`.${this.datatable.style.scopeClass} .dt-scrollable`).css({
                "max-height": "calc(500vh - 400px)",
                overflow: "auto visible",
            });

            if (this.transactions.length > 0) {
                console.log(this.datatable);
                this.$supplier_level_dt.fieldobj.$wrapper.show();
            } else {
                this.$supplier_level_dt.fieldobj.$wrapper.hide();
            }
        } else if (this.$invoice_level_dt) {
            this.datatable = new frappe.DataTable(
                this.$invoice_level_dt.fieldobj.$wrapper.get(0),
                datatable_options
            );

            $(`.${this.datatable.style.scopeClass} .dt-scrollable`).css({
                "max-height": "calc(500vh - 400px)",
                overflow: "auto visible",
            });

            if (this.transactions.length > 0) {
                console.log(this.datatable);
                this.$invoice_level_dt.fieldobj.$wrapper.show();
            } else {
                this.$invoice_level_dt.fieldobj.$wrapper.hide();
            }
        }
    }

    get_checked_items(only_docnames) {
        console.log(this.datatable);
        const indexes = this.datatable.rowmanager.getCheckedRows();
        console.log(indexes);
        const items = indexes
            .map(i => this.transactions[i])
            .filter(i => i != undefined);

        if (only_docnames) {
            return items.map(d => d.name);
        }
        console.log(items);
        return items;
    }

    set_listeners() {
        var me = this;
        // $(`.${this.datatable.style.scopeClass} .dt-scrollable`).on(
        // 	"click",
        // 	`.btn`,
        // 	function () {
        // 		me.dialog_manager.show_dialog(
        // 			$(this).attr("data-name"),
        // 			(bank_transaction) => me.update_dt_cards(bank_transaction)
        // 		);
        // 		return true;
        // 	}
        // );
    }
};
