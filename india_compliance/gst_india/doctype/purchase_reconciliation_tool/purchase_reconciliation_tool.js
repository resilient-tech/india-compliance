// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

// TODO: change the namespace
// TODO: replace the demo data
frappe.provide("reco_tool");

const reco_tool_detail_view_fields = ["bill_no", "bill_date", "cgst", "sgst", "igst", "cess", "is_reverse_charge", "place_of_supply"];

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
        patch_set_active_tab(frm);
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
            ? frm.add_custom_button(__("Download"), () => show_gstr_dialog(frm))
            : frm.add_custom_button(__("Upload"), () => show_gstr_dialog(frm, false));

        // add custom buttons
        if (!frm.purchase_reconciliation_tool?.data) return;
        if (frm.get_active_tab()?.df.fieldname == "invoice_tab") {
            frm.add_custom_button(
                __("Unlink"),
                () => unlink_documents(frm),
                __("Actions")
            );
            frm.add_custom_button("dropdown-divider", () => {}, __("Actions"));
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
    },

    purchase_period(frm) {
        fetch_date_range(frm, "purchase");
    },

    inward_supply_period(frm) {
        fetch_date_range(frm, "inward_supply");
    },

    after_save(frm) {
        frm.purchase_reconciliation_tool.refresh(
            frm.doc.__onload?.reconciliation_data?.data
        );
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
        this.data = [];
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
        this.filter_button = $(`<div class="filter-selector">
			<button class="btn btn-default btn-sm filter-button">
				<span class="filter-icon">
					${frappe.utils.icon("filter")}
				</span>
				<span class="button-label hidden-xs">
					${__("Filter")}
				<span>
			</button>
		</div>`).appendTo(this.$wrapper.find(".form-tabs-list"));

        this.filter_group = new ic.FilterGroup({
            doctype: "Purchase Reconciliation Tool",
            filter_button: this.filter_button,
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
                fieldname: "isup_match_status",
                fieldtype: "Select",
                options: [
                    "Exact Match",
                    "Suggested Match",
                    "Mismatch",
                    "Manual Match",
                    "Missing in 2A/2B",
                    "Missing in PR",
                ],
            },
            {
                label: "Action",
                fieldname: "isup_action",
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
                fieldname: "isup_classification",
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

    apply_filters(force) {
        const has_filters = this.filter_group.filters.length > 0;
        if (!has_filters) {
            this.filters = null;
            this.filtered_data = this.data;
            return;
        }

        const filters = this.filter_group.get_filters();
        if (!force && this.filters === filters) return;

        this.filters = filters;
        this.filtered_data = this.data.filter(row => {
            return filters.every(filter =>
                ic.FILTER_OPERATORS[filter[2]](filter[3] || "", row[filter[1]] || "")
            );
        });
    }

    render_data_tables() {
        this._tabs.forEach(tab => {
            this.tabs[`${tab}_tab`] = new ic.DataTableManager({
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
            let data = me.mapped_invoice_data[$(this).attr("data-name")];
            show_detailed_dialog(me, data);
        });
    }

    get_summary_data() {
        const data = {};
        this.filtered_data.forEach(row => {
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
                width: 120,
                align: "center",
            },
            {
                label: "Count <br>Purchase Docs",
                fieldname: "count_pur_docs",
                width: 120,
                align: "center",
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_diff",
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
                label: "% Action Taken",
                fieldname: "action_taken",
                width: 120,
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
        this.filtered_data.forEach(row => {
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
                label: "Supplier Name",
                fieldname: "supplier_name",
                fieldtype: "Link",
                width: 200,
                _value: (value, column, data) => {
                    // if (data && column.field === "supplier_name") {
                    //     column.docfield.link_onclick = `reco_tool.apply_filters(${JSON.stringify(
                    //         {
                    //             tab: "invoice_tab",
                    //             filters: {
                    //                 supplier_name: data.supplier_gstin,
                    //             },
                    //         }
                    //     )})`;
                    // }

                    return `
                            ${data.supplier_name}
                            <br />
                            <span style="font-size: 0.9em">
                                ${data.supplier_gstin || ""}
                            </span>
                        `;
                },
            },
            {
                label: "Count <br>2A/2B Docs",
                fieldname: "count_isup_docs",
                align: "center",
                width: 120,
            },
            {
                label: "Count <br>Purchase Docs",
                fieldname: "count_pur_docs",
                align: "center",
                width: 120,
            },
            {
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                fieldname: "taxable_value_diff",
                align: "center",
                width: 150,
                _value: (...args) => {
                    return format_number(args[0]);
                },
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
                label: "% Action <br>Taken",
                fieldname: "action_taken",
                align: "center",
                width: 120,
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
        this.mapped_invoice_data = {};
        this.filtered_data.forEach(row => {
            this.mapped_invoice_data[get_hash(row)] = row;
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
                fieldname: "supplier_name",
                width: 150,
                _value: (...args) => {
                    return `${args[2].supplier_name}
                            <br />
                            <span style="font-size: 0.9em">
                                ${args[2].supplier_gstin || ""}
                            </span>`;
                },
            },
            {
                label: "Bill No.",
                fieldname: "bill_no",
            },
            {
                label: "Date",
                fieldname: "bill_date",
            },
            {
                label: "Match Status",
                fieldname: "isup_match_status",
                width: 120,
            },
            {
                label: "Purchase <br>Invoice",
                fieldname: "name",
                fieldtype: "Link",
                doctype: "Purchase Invoice",
                align: "center",
                width: 120,
            },
            {
                label: "GST Inward <br>Supply",
                fieldname: "isup_name",
                fieldtype: "Link",
                doctype: "GST Inward Supply",
                align: "center",
                width: 120,
            },
            {
                fieldname: "taxable_value_diff",
                label: "Taxable Amount Diff <br>2A/2B - Purchase",
                width: 150,
                align: "center",
                _value: (...args) => {
                    return format_number(args[0]);
                },
            },
            {
                label: "Tax Difference <br>2A/2B - Purchase",
                fieldname: "tax_diff",
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

// reco_tool.apply_filters = function ({ tab, filters }) {
//     if (!cur_frm) return;

//     // Switch to the tab
//     const { tabs } = cur_frm.purchase_reconciliation_tool;
//     tab = tabs && (tabs[tab] || Object.values(tabs).find(tab => tab.is_active()));
//     tab.set_active();

//     // apply filters
//     const _filters = {};
//     for (const [fieldname, filter] of Object.entries(filters)) {
//         const column = tab.data_table_manager.get_column(fieldname);
//         column.$filter_input.value = filter;
//         _filters[column.colIndex] = filter;
//     }

//     tab.data_table_manager.datatable.columnmanager.applyFilter(_filters);
// };

function get_icon(value, column, data, icon) {
    /**
     * Returns custom ormated value for the row.
     * @param {string} value        Current value of the row.
     * @param {object} column       All properties of current column
     * @param {object} data         All values in its core form for current row
     * @param {string} icon         Return icon (font-awesome) as the content
     */
    const hash = get_hash(data);
    return `<button class="btn ${icon}" title="hello" data-name="${hash}">
                <i class="fa fa-${icon}"></i>
            </button>`;
}

function get_hash(data) {
    if (data.name || data.isup_name) return data.name + "~" + data.isup_name;
}

function patch_set_active_tab(frm) {
    const set_active_tab = frm.set_active_tab;
    frm.set_active_tab = function (...args) {
        set_active_tab.apply(this, args);
        frm.refresh();
    };
}

reco_tool.link_documents = async function (frm, pur_name, isup_name, alert = true) {
    if (frm.get_active_tab()?.df.fieldname != "invoice_tab") return;

    // link documents & update data.
    const { message: r } = await frm.call("link_documents", { pur_name, isup_name });
    const reco_tool = frm.purchase_reconciliation_tool;
    const new_data = reco_tool.data.filter(
        row => !(row.name == pur_name || row.isup_name == isup_name)
    );
    new_data.push(...r);

    reco_tool.refresh(new_data);
    if (alert)
        after_successful_action(frm.purchase_reconciliation_tool.tabs.invoice_tab);
};

function unlink_documents(frm) {
    if (frm.get_active_tab()?.df.fieldname != "invoice_tab") return;
    const { invoice_tab } = frm.purchase_reconciliation_tool.tabs;
    const selected_rows = invoice_tab.get_checked_items();

    // validate selected rows
    selected_rows.forEach(row => {
        if (row.isup_match_status.includes("Missing"))
            frappe.throw(
                "You have selected rows where no match is available. Please remove them before unlinking."
            );
    });

    // unlink documents & update table
    frm.call("unlink_documents", selected_rows);
    const unlinked_docs = [
        ...get_unlinked_docs(selected_rows),
        ...get_unlinked_docs(selected_rows, true),
    ];
    const reco_tool = frm.purchase_reconciliation_tool;
    const new_data = reco_tool.data.filter(
        row => !has_matching_row(row, selected_rows)
    );
    new_data.push(...unlinked_docs);
    reco_tool.refresh(new_data);
    after_successful_action(invoice_tab);
}

function get_unlinked_docs(selected_rows, isup = false) {
    const fields_to_update = [
        "bill_no",
        "bill_date",
        "place_of_supply",
        "is_reverse_charge",
    ];

    return deepcopy(selected_rows).map(row => {
        if (isup) row.name = null;
        else row.isup_name = null;

        if (isup)
            fields_to_update.forEach(field => {
                row[field] = row[`isup_${field}`];
            });

        row.tax_diff = "";
        row.taxable_value_diff = "";
        row.differences = "";

        if (!(row.isup_action == "Ignore" || (isup && row.isup_action == "Pending")))
            row.isup_action = "No Action";

        if (!isup) row.isup_match_status = "Missing in 2A/2B";
        else row.isup_match_status = "Missing in PR";

        return row;
    });
}

function deepcopy(array) {
    return JSON.parse(JSON.stringify(array));
}

function apply_action(frm, action) {
    const active_tab = frm.get_active_tab()?.df.fieldname;
    if (!active_tab) return;

    const tab = frm.purchase_reconciliation_tool.tabs[active_tab];
    const selected_rows = tab.get_checked_items();

    // validate selected rows
    if (action != "Ignore")
        selected_rows.forEach(row => {
            if (row.isup_match_status == "Missing in 2A/2B")
                frappe.throw(
                    "You can only apply Ignore action on rows where data is Missing in 2A/2B. Please remove them before applying this action."
                );
        });

    // get affected rows
    const { filtered_data, data } = frm.purchase_reconciliation_tool;
    const affected_rows = get_affected_rows(active_tab, selected_rows, filtered_data);

    // update affected rows to backend and frontend
    frm.call("apply_action", { data: affected_rows, action });
    data.forEach(row => {
        if (has_matching_row(row, affected_rows)) row.isup_action = action;
    });

    frm.purchase_reconciliation_tool.refresh(data);
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
            inv =>
                selection.filter(row => row.isup_match_status == inv.isup_match_status)
                    .length
        );
}

function set_value_color (wrapper, data) {
    reco_tool_detail_view_fields.forEach(field => {
        if (!data.name || !data.isup_name) return;

        if (!in_list(["place_of_supply", "is_reverse_charge"], field)) return;

        if (data[field] != data[`isup_${field}`]) {
            wrapper.find(`[data-label='${field}'], [data-label='isup_${field}']`).addClass('not-matched');
        }
    });
}

function show_detailed_dialog (me, data) {
    const mapped_data = get_mapped_invoice_data(data);

    var d = new frappe.ui.Dialog({
        title: "GSTR 2A / 2B vs Purchase Register",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "purchase_reco_tool_cards",
            },
            ...get_document_link_fields(me, mapped_data),
            {
                fieldtype: "HTML",
                fieldname: "detail_view",
            }
        ],
    });
    _add_custom_actions(d, me, mapped_data);

    const detail_view = d.fields_dict.detail_view.$wrapper;

    // Render detail view dialog data
    render_cards(mapped_data, d.fields_dict.purchase_reco_tool_cards.$wrapper);
    detail_view.html(get_content_html(mapped_data));
    set_value_color(detail_view, mapped_data);

    d.show();
};

function get_mapped_invoice_data(data) {
    let mapped_data = Object.assign({}, data);
    mapped_data.supplier_gstin = mapped_data.supplier_gstin.replace(/\s+/g, '');

    reco_tool_detail_view_fields.forEach(field => {
        if (field == "is_reverse_charge") {
            mapped_data[field] = mapped_data[field] ? "Yes" : "No";
            mapped_data[`isup_${field}`] = mapped_data[`isup_${field}`] ? "Yes" : "No";
        }
        if (data.isup_name && !data.name) {
            delete mapped_data[field];
        } else if (data.name && !data.isup_name) {
            delete mapped_data[`isup_${field}`];
        }
    });

    return mapped_data;
}

function get_document_link_fields(me, data) {
    let doctype = "";
    let field_prefix = "";
    let date_filters = {
        'supplier_gstin': data.supplier_gstin
    };

    if (data.name && !data.isup_name) {
        doctype = "GST Inward Supply";
        field_prefix = "inward_supply";
    }
    else if (!data.name && data.isup_name) {
        doctype = 'Purchase Invoice';
        field_prefix = "purchase";
    }

    const date_range = get_date_range(me, field_prefix);

    doctype == "GST Inward Supply"
        ? date_filters.bill_date = ["between", date_range]
        : date_filters.posting_date = ["between", date_range];

    const fields = [
        {
            label: "GSTIN",
            fieldtype: "Data",
            fieldname: "supplier_gstin",
            default: data.supplier_gstin,
        },
        {
            fieldtype: "Column Break",
            fieldname: "column_break_1",
        },
        {
            label: "Date Range",
            fieldtype: "DateRange",
            fieldname: "date_range",
            default: date_range,
        },
        {
            fieldtype: "Section Break",
            fieldname: "section_break_1",
        },
        {
        label: `Link To (${doctype}):`,
        fieldtype: "Link",
        fieldname: "link_action",
        options: doctype,
        get_query() {
                return {
                    filters: date_filters
                };
            }
        },
    ];

    return data.name && data.isup_name ? [] : fields
};

function get_date_range(me, field_prefix) {
    const doc = me.frm.doc;
    const from_date_field = field_prefix + "_from_date";
    const to_date_field = field_prefix + "_to_date";

    const from_date = moment(doc[from_date_field]).format("YYYY-MM-DD");
    const to_date = moment(doc[to_date_field]).format("YYYY-MM-DD");

    return [from_date, to_date];
}

function _add_custom_actions(d, me, data) {
    const frm = me.frm;
    let actions = [];
    const match_actions = data.name && data.isup_name
        ? ["Unlink", "Accept My Values", "Accept Supplier Values", "Pending"]
        : [];

    const pr_actions = data.isup_match_status == "Missing in PR"
        ? ["Create", "Link", "Pending"]
        : [];

    const isup_actions = data.isup_match_status == "Missing in 2A/2B"
        ? ["Link"]
        : [];

    actions.push(...pr_actions, ...isup_actions, ...match_actions, "Ignore");

    actions.forEach(action => {
        let btn_css_class = get_button_css(action);

        d.add_custom_action(action, () => {
            apply_custom_action(frm, data, action)
            d.hide();
        },
        `mr-2 ${btn_css_class}`);

        if (btn_css_class == 'btn-secondary') return;
        d.$wrapper.find('.btn.btn-secondary').removeClass('btn-secondary');
    })
    d.$wrapper.find(".modal-footer").css("flex-direction", "inherit");
}

function get_button_css(action) {
    if (action == "Unlink") return "btn-danger";
    if (action == "Pending") return "btn-secondary";
    if (action == "Ignore") return "btn-secondary";
    if (action == "Create") return "btn-primary";
    if (action == "Link") return "btn-primary";
    if (action == "Accept My Values") return "btn-primary";
    if (action == "Accept Supplier Values") return "btn-primary";
}

function apply_custom_action(frm, data, action) {
    if (action == "Unlink") {
        unlink_documents(frm, data);
    } else if (action == "Link") {
        reco_tool.link_documents(frm, data.name, data.isup_name,true);
    } else if (action == "Create") {
        create_new_purchase_invoice(data, frm.doc.company, frm.doc.company_gstin);
    } else {
        apply_action(frm, action);
    }
}

function render_cards(data, purchase_reco_tool_cards) {
    const doc_missing = in_list(["Missing in PR", "Missing in 2A/2B"], data.isup_match_status);

    if (doc_missing) return;

    let cards =  [
        {
            value: data.tax_diff,
            label: "Tax Difference",
            datatype: "Currency",
            currency: frappe.boot.sysdefaults.currency,
        },
        {
            value: data.taxable_value_diff,
            label: "Taxable Value Difference",
            datatype: "Currency",
            currency: frappe.boot.sysdefaults.currency,
        },
    ];

    new ic.NumberCardManager({
        $wrapper: purchase_reco_tool_cards,
        cards: cards,
        condition: data.tax_diff == data.taxable_value_diff,
    });
}

function get_content_html(data) {
    const doc_links = {
        purchase_link: get_doc_link("Purchase Invoice", data.name),
        isup_link: get_doc_link("GST Inward Supply", data.isup_name),
    }

    data = { ...data, ...doc_links };

    return frappe.render_template('reco_tool_detail_view', {
        data: data,
    });
}

function get_doc_link(doctype, name) {
    return name ? frappe.utils.get_form_link(doctype, name, true) : "-";
}
async function create_new_purchase_invoice(inward_supply, company, company_gstin) {
    if (inward_supply.isup_match_status != "Missing in PR") return;

    const { message: supplier } = await frappe.call({
        method: "india_compliance.gst_india.utils.get_party_for_gstin",
        args: {
            gstin: inward_supply.supplier_gstin,
        },
    });

    let company_address;
    await frappe.model.get_value(
        "Address",
        { gstin: company_gstin, is_your_company_address: 1 },
        "name",
        r => (company_address = r.name)
    );

    await frappe.new_doc("Purchase Invoice");
    const pur_frm = cur_frm;

    pur_frm.doc.bill_no = inward_supply.isup_bill_no;
    pur_frm.doc.bill_date = inward_supply.isup_bill_date;
    pur_frm.doc.is_reverse_charge = inward_supply.isup_is_reverse_charge;

    _set_value(pur_frm, {
        company: company,
        supplier: supplier,
        shipping_address: company_address,
        billing_address: company_address,
    });

    function _set_value(frm, values) {
        for (const key in values) {
            if (values[key] == frm.doc[key]) continue;
            frm.set_value(key, values[key]);
        }
    }

    // validated this on save
    pur_frm._inward_supply = {
        company: company,
        company_gstin: company_gstin,
        isup_name: inward_supply.isup_name,
        supplier_gstin: inward_supply.supplier_gstin,
        bill_no: inward_supply.isup_bill_no,
        bill_date: inward_supply.isup_bill_date,
        is_reverse_charge: inward_supply.isup_is_reverse_charge,
        place_of_supply: inward_supply.isup_place_of_supply,
        cgst: inward_supply.isup_cgst,
        sgst: inward_supply.isup_sgst,
        igst: inward_supply.isup_igst,
        cess: inward_supply.isup_cess,
        taxable_value: inward_supply.isup_taxable_value,
    };
}

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
