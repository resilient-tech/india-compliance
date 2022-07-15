// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt
frappe.provide("reco_tool");

const ReturnType = {
    GSTR2A: "GSTR2a",
    GSTR2B: "GSTR2b",
};

frappe.ui.form.on("Purchase Reconciliation Tool", {
    setup(frm) {
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

        frm.add_custom_button("Download", () => show_gstr_dialog(frm));
        frm.add_custom_button("Upload", () => show_gstr_dialog(frm, false));

        if (frm.doc.company) set_gstin_options(frm);
    },

    purchase_period(frm) {
        fetch_date_range(frm, "purchase");
    },

    inward_supply_period(frm) {
        fetch_date_range(frm, "inward_supply");
    },
});

async function set_gstin_options(frm) {
    const { query, params } = ic.get_gstin_query(frm.doc.company);
    const { message } = await frappe.call({
        method: query,
        args: params,
    });

    if (!message) return;
    const gstin_field = frm.get_field("company_gstin");
    gstin_field.set_data(message);
    return message;
}

class PurchaseReconciliationTool {
    constructor(frm) {
        this.frm = frm;
        this.render_tab_group();
    }

    render_tab_group() {
        this.tabGroup = new frappe.ui.FieldGroup({
            fields: [
                // this field is a hack for the FieldGroup(Layout) to not render default tab
                {
                    fieldtype: "Data",
                    hidden: 1,
                },
                {
                    label: "Summary",
                    fieldtype: "Tab Break",
                    fieldname: "summary_tab_break",
                    active: 1,
                },
                {
                    fieldtype: "HTML",
                    fieldname: "summary",
                    options: "summary",
                },
                {
                    label: "Supplier Level",
                    fieldtype: "Tab Break",
                    fieldname: "supplier_tab_break",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "supplier_level",
                    options: "supplier_level",
                },
                {
                    label: "Invoice Level",
                    fieldtype: "Tab Break",
                    fieldname: "invoice_tab_break",
                },
                {
                    fieldtype: "HTML",
                    fieldname: "invoice_level",
                    options: "invoice_level",
                },
            ],
            body: this.frm.get_field("summary_data").$wrapper,
            frm: this.frm,
        });

        this.tabGroup.make();
        this.tabGroup.tabs[0].toggle(true);
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
                console.log(dialog.get_value("fiscal_year"));
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
