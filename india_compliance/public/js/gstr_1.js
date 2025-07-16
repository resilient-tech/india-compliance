import "./components/filter_group";
import "./components/data_table_manager";
import "./components/view_group";

frappe.provide("gstr_1");

const GSTR1_Category = {
    B2B: "B2B, SEZ, DE",
    EXP: "Exports",
    B2CL: "B2C (Large)",
    B2CS: "B2C (Others)",
    NIL_EXEMPT: "Nil-Rated, Exempted, Non-GST",
    CDNR: "Credit/Debit Notes (Registered)",
    CDNUR: "Credit/Debit Notes (Unregistered)",
    // Other Categories
    AT: "Advances Received",
    TXP: "Advances Adjusted",
    HSN: "HSN Summary",
    DOC_ISSUE: "Document Issued",
};

const GSTR1_SubCategory = {
    B2B_REGULAR: "B2B Regular",
    B2B_REVERSE_CHARGE: "B2B Reverse Charge",
    SEZWP: "SEZ With Payment of Tax",
    SEZWOP: "SEZ Without Payment of Tax",
    DE: "Deemed Exports",
    EXPWP: "Export With Payment of Tax",
    EXPWOP: "Export Without Payment of Tax",
    B2CL: "B2C (Large)",
    B2CS: "B2C (Others)",
    NIL_EXEMPT: "Nil-Rated, Exempted, Non-GST",
    CDNR: "Credit/Debit Notes (Registered)",
    CDNUR: "Credit/Debit Notes (Unregistered)",

    AT: "Advances Received",
    TXP: "Advances Adjusted",
    HSN: "HSN Summary",
    HSN_B2B: "HSN Summary - B2B",
    HSN_B2C: "HSN Summary - B2C",
    DOC_ISSUE: "Document Issued",

    SUPECOM_52: "Liable to collect tax u/s 52(TCS)",
    SUPECOM_9_5: "Liable to pay tax u/s 9(5)",
};

const INVOICE_TYPE = {
    [GSTR1_Category.B2B]: [
        GSTR1_SubCategory.B2B_REGULAR,
        GSTR1_SubCategory.B2B_REVERSE_CHARGE,
        GSTR1_SubCategory.SEZWP,
        GSTR1_SubCategory.SEZWOP,
        GSTR1_SubCategory.DE,
    ],
    [GSTR1_Category.B2CL]: [GSTR1_SubCategory.B2CL],
    [GSTR1_Category.EXP]: [GSTR1_SubCategory.EXPWP, GSTR1_SubCategory.EXPWOP],
    [GSTR1_Category.NIL_EXEMPT]: [GSTR1_SubCategory.NIL_EXEMPT],
    [GSTR1_Category.CDNR]: [GSTR1_SubCategory.CDNR],
    [GSTR1_Category.CDNUR]: [GSTR1_SubCategory.CDNUR],
    [GSTR1_Category.AT]: [GSTR1_SubCategory.AT],
    [GSTR1_Category.TXP]: [GSTR1_SubCategory.TXP],
    [GSTR1_Category.HSN]: [GSTR1_SubCategory.HSN],
    [GSTR1_Category.DOC_ISSUE]: [GSTR1_SubCategory.DOC_ISSUE],
};

const GSTR1_DataField = {
    TRANSACTION_TYPE: "transaction_type",
    CUST_GSTIN: "customer_gstin",
    ECOMMERCE_GSTIN: "ecommerce_gstin",
    CUST_NAME: "customer_name",
    DOC_DATE: "document_date",
    DOC_NUMBER: "document_number",
    DOC_TYPE: "document_type",
    DOC_VALUE: "document_value",
    POS: "place_of_supply",
    DIFF_PERCENTAGE: "diff_percentage",
    REVERSE_CHARGE: "reverse_charge",
    TAXABLE_VALUE: "total_taxable_value",
    TAX_RATE: "tax_rate",
    IGST: "total_igst_amount",
    CGST: "total_cgst_amount",
    SGST: "total_sgst_amount",
    CESS: "total_cess_amount",
    UPLOAD_STATUS: "upload_status",

    SHIPPING_BILL_NUMBER: "shipping_bill_number",
    SHIPPING_BILL_DATE: "shipping_bill_date",
    SHIPPING_PORT_CODE: "shipping_port_code",

    EXEMPTED_AMOUNT: "exempted_amount",
    NIL_RATED_AMOUNT: "nil_rated_amount",
    NON_GST_AMOUNT: "non_gst_amount",

    HSN_CODE: "hsn_code",
    DESCRIPTION: "description",
    UOM: "uom",
    QUANTITY: "quantity",

    FROM_SR: "from_sr_no",
    TO_SR: "to_sr_no",
    TOTAL_COUNT: "total_count",
    DRAFT_COUNT: "draft_count",
    CANCELLED_COUNT: "cancelled_count",
};

class TabManager {
    DEFAULT_NO_DATA_MESSAGE = __("No Data");
    CATEGORY_COLUMNS = {};
    DEFAULT_SUMMARY = {
        // description: "",
        no_of_records: 0,
        total_taxable_value: 0,
        total_igst_amount: 0,
        total_cgst_amount: 0,
        total_sgst_amount: 0,
        total_cess_amount: 0,
    };

    constructor(instance, wrapper, summary_view_callback, detailed_view_callback) {
        this.DEFAULT_TITLE = "";
        this.DEFAULT_SUBTITLE = "";
        this.creation_time_string = "";

        this.instance = instance;
        this.wrapper = wrapper;
        this.summary_view_callback = summary_view_callback;
        this.detailed_view_callback = detailed_view_callback;

        this.reset_data();
        this.setup_wrapper();
        this.setup_datatable(wrapper);
        this.setup_footer(wrapper);
    }

    reset_data() {
        this.data = {}; // Raw Data
        this.filtered_data = {}; // Filtered Data / Detailed View
        this.summary = {};
    }

    refresh_data(data, summary_data, status) {
        this.data = data;
        this.summary = summary_data;
        this.status = status;
        this.rounding_difference = this.data?.rounding_difference[0];
        this.remove_tab_custom_buttons();
        this.setup_actions();
        this.datatable.refresh(this.summary, null, this.get_no_data_message());
        this.set_default_title();
        this.set_creation_time_string();
    }

    refresh_no_data_message() {
        this.datatable.refresh(null, null, this.get_no_data_message());
    }

    refresh_view(view, category, filters) {
        if (!category && view === "Detailed") return;

        this.filter_category = category;
        let subtitle = "";

        if (view === "Detailed") {
            this.filter_fieldnames = this.instance.filter_fields.map(
                filter => filter.fieldname
            );

            const columns_func = this.CATEGORY_COLUMNS[category];
            if (!columns_func) return;

            this.category_columns = columns_func.call(this);
            this.setup_datatable(
                this.wrapper,
                this.filter_data(this.data[category], filters),
                this.category_columns
            );
            this.set_title(category, null, true);
        } else if (view === "Summary") {
            this.setup_datatable(
                this.wrapper,
                this.summary,
                this.get_summary_columns()
            );
            subtitle = this.DEFAULT_SUBTITLE;
            this.set_title(this.DEFAULT_TITLE, subtitle);
        }

        this.setup_footer(this.wrapper);
        this.set_creation_time_string();
    }

    filter_data(data, filters) {
        if (!data) return [];
        if (!filters || !filters.length) return data;

        return data.filter(row => {
            return filters.every(filter =>
                india_compliance.FILTER_OPERATORS[filter[2]](
                    filter[3] || "",
                    row[filter[1]] || ""
                )
            );
        });
    }

    // SETUP

    set_title(title, subtitle, with_back_button = false) {
        if (title) this.wrapper.find(".tab-title-text").text(title);
        else this.wrapper.find(".tab-title-text").html("&nbsp");

        if (subtitle) this.wrapper.find(".tab-subtitle-text").text(subtitle);
        else this.wrapper.find(".tab-subtitle-text").html("");

        if (with_back_button) this.wrapper.find(".tab-back-button").show();
        else this.wrapper.find(".tab-back-button").hide();
    }

    set_default_title() {
        this.set_title(this.DEFAULT_TITLE, this.DEFAULT_SUBTITLE);
    }

    setup_wrapper() {
        this.wrapper.append(`
            <div class="m-3 d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    <div class="tab-back-button mr-4">
                        <a><i class="fa fa-arrow-left"></i></a>
                    </div>
                    <div>
                        <div class="tab-title-text">&nbsp</div>
                        <div class="tab-subtitle-text"></div>
                    </div>
                </div>
                <div class="custom-button-group page-actions custom-actions hidden-xs hidden-md"></div>
            </div>
            <div class="data-table"></div>
            <div class="report-footer" style="padding: var(--padding-sm)">
                <button class="btn btn-xs btn-default expand" data-action="expand_all_rows">
                    ${__("Expand All")}</button>
                <button class="btn btn-xs btn-default collapse" data-action="collapse_all_rows">
                    ${__("Collapse All")}</button>
            </div>
        `);

        this.setup_back_button_listener();
    }

    setup_back_button_listener() {
        this.wrapper.find(".tab-back-button").on("click", () => {
            this.instance.show_summary_view();
        });
    }

    setup_datatable(wrapper, data, columns) {
        const _columns = columns || this.get_summary_columns();
        const _data = data || [];
        const treeView = this.instance.active_view === "Summary";

        this.datatable = new india_compliance.DataTableManager({
            $wrapper: wrapper.find(".data-table"),
            columns: _columns,
            data: _data,
            options: {
                showTotalRow: true,
                checkboxColumn: false,
                treeView: treeView,
                noDataMessage: this.get_no_data_message(),
                headerDropdown: [
                    {
                        label: "Collapse All Node",
                        action: () => {
                            this.datatable.datatable.rowmanager.collapseAllNodes();
                        },
                    },
                    {
                        label: "Expand All Node",
                        action: () => {
                            this.datatable.datatable.rowmanager.expandAllNodes();
                        },
                    },
                ],
                hooks: {
                    columnTotal: (_, row) => {
                        if (this.instance.active_view !== "Summary") return null;

                        if (row.colIndex === 1)
                            return (row.content = "Total Liability");

                        const column_field = row.column.fieldname;
                        if (!this.summary) return null;

                        const total = this.summary.reduce((acc, row) => {
                            if (
                                row.consider_in_total_taxable_value &&
                                ["no_of_records", "total_taxable_value"].includes(
                                    column_field
                                )
                            )
                                acc += row[column_field] || 0;
                            else if (row.consider_in_total_tax)
                                acc += row[column_field] || 0;

                            return acc;
                        }, 0);

                        return total;
                    },
                },
            },
            ...this.get_additional_datatable_config(),
        });

        this.setup_datatable_listeners(treeView);
    }

    get_additional_datatable_config() {
        // Override this method in subclasses to provide additional configuration
        return {};
    }

    setup_datatable_listeners(isSummaryView) {
        const me = this;

        // Summary View
        if (isSummaryView) {
            this.datatable.$datatable.on("click", ".description", async function (e) {
                e.preventDefault();

                const summary_description = $(this).text();
                me.summary_view_callback &&
                    me.summary_view_callback(summary_description);
            });
            return;
        }

        // Detailed View
        this.instance.filter_fields.forEach(field => {
            this.datatable.$datatable.on("click", `.${field.fieldname}`, function (e) {
                e.preventDefault();

                const fieldname = field.fieldname;
                const value = $(this).text();
                me.detailed_view_callback &&
                    me.detailed_view_callback(fieldname, value);
            });
        });
    }

    setup_footer(wrapper) {
        const treeView = this.instance.active_view === "Summary";
        if (!treeView) {
            $(wrapper).find("[data-action=collapse_all_rows]").hide();
            $(wrapper).find("[data-action=expand_all_rows]").hide();
        } else {
            $(wrapper).find("[data-action=collapse_all_rows]").show();
            $(wrapper).find("[data-action=expand_all_rows]").hide();
        }

        this.setup_footer_actions(wrapper);
    }

    setup_footer_actions(wrapper) {
        const me = this;
        ["expand", "collapse"].forEach(action => {
            $(wrapper).on("click", `.${action}`, function (e) {
                e.preventDefault();
                me.datatable.datatable.rowmanager[`${action}AllNodes`]();
                $(wrapper).find("[data-action=collapse_all_rows]").toggle();
                $(wrapper).find("[data-action=expand_all_rows]").toggle();
            });
        });
    }

    set_creation_time_string() {
        const creation_time_string = this.get_creation_time_string();
        if (!creation_time_string) return;

        if ($(this.wrapper).find(".creation-time").length)
            $(this.wrapper).find(".creation-time").remove();

        this.wrapper
            .find(".report-footer")
            .append(
                `<div class="creation-time text-muted float-right">${creation_time_string}</div>`
            );
    }

    get_creation_time_string() {
        if (!this.data.creation) return;

        const creation = frappe.utils.to_title_case(
            frappe.datetime.prettyDate(this.data.creation)
        );

        return `Created ${creation}`;
    }

    // UTILS

    add_tab_custom_button(label, action) {
        let button = this.wrapper.find(
            `button[data-label="${encodeURIComponent(label)}"]`
        );
        if (button.length) return;

        $(`
            <button
            class="btn btn-default ellipsis"
            data-label="${encodeURIComponent(label)}">
                ${label}
            </button>
        `)
            .appendTo(this.wrapper.find(".custom-button-group"))
            .on("click", action);
    }

    remove_tab_custom_buttons() {
        this.wrapper.find(".custom-button-group").empty();
    }

    format_summary_table_cell(args) {
        const isDescriptionCell = args[1]?.id === "description";
        let value = args[0];

        if (args[1]?._fieldtype === "Currency") value = format_currency(value);
        else if (args[1]?._fieldtype === "Float") value = format_number(value);

        value =
            args[2]?.indent == 0
                ? `<strong>${value}</strong>`
                : isDescriptionCell
                ? `<a href="#" class="description">
                    <p style="padding-left: 15px">${value}</p>
                    </a>`
                : value;

        return value;
    }

    format_detailed_table_cell(args) {
        /**
         * Update fieldname as a class to the cell
         * and make it clickable.
         *
         * This is used to simplify filtering of data
         */
        let value = frappe.format(...args);

        if (this.filter_fieldnames.includes(args[1]?.id))
            value = `
                <a href="#" class="${args[1]?.id}">
                    ${value}
                </a>`;

        return value;
    }

    get_icon(value, column, data, icon) {
        if (!data) return "";
        return `
        <button
            class="btn ${icon} reconcile-row"
            data-row-index='${data.idx}'
        >
            <i class="fa fa-${icon}"></i>
        </button>`;
    }

    get_no_data_message() {
        return this.DEFAULT_NO_DATA_MESSAGE;
    }
}

class GSTR1_TabManager extends TabManager {
    // COLUMNS
    get_summary_columns() {
        return [
            {
                name: "Description",
                fieldname: "description",
                width: 300,
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "Total Docs",
                fieldname: "no_of_records",
                _fieldtype: "Float",
                width: 100,
                align: "center",
                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                _fieldtype: "Float",
                width: 180,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataField.CGST,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataField.SGST,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                _fieldtype: "Float",
                width: 150,

                _value: (...args) => this.format_summary_table_cell(args),
            },
        ];
    }

    get_invoice_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer GSTIN",
                fieldname: GSTR1_DataField.CUST_GSTIN,
                width: 160,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            {
                name: "Reverse Charge",
                fieldname: GSTR1_DataField.REVERSE_CHARGE,
                width: 120,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            ...this.get_tax_columns(),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_export_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Invoice Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Invoice Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            {
                name: "Invoice Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            {
                name: "Shipping Bill Number",
                fieldname: GSTR1_DataField.SHIPPING_BILL_NUMBER,
                width: 150,
            },
            {
                name: "Shipping Bill Date",
                fieldname: GSTR1_DataField.SHIPPING_BILL_DATE,
                width: 120,
            },
            {
                name: "Port Code",
                fieldname: GSTR1_DataField.SHIPPING_PORT_CODE,
                width: 100,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            ...this.get_igst_tax_columns(),
            {
                name: "Invoice Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_document_columns(with_tax_rate) {
        // `Transaction Type` + Invoice Columns with `Document` as title instead of `Invoice`
        return [
            ...this.get_detail_view_column(),
            {
                name: "Transaction Type",
                fieldname: GSTR1_DataField.TRANSACTION_TYPE,
                width: 100,
            },
            {
                name: "Document Date",
                fieldname: GSTR1_DataField.DOC_DATE,
                fieldtype: "Date",
                width: 120,
            },
            {
                name: "Document Number",
                fieldname: GSTR1_DataField.DOC_NUMBER,
                fieldtype: "Link",
                options: "Sales Invoice",
                width: 160,
            },
            {
                name: "Customer GSTIN",
                fieldname: GSTR1_DataField.CUST_GSTIN,
                width: 160,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Customer Name",
                fieldname: GSTR1_DataField.CUST_NAME,
                width: 200,
            },
            {
                name: "Document Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 150,
            },
            {
                name: "Reverse Charge",
                fieldname: GSTR1_DataField.REVERSE_CHARGE,
                width: 120,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            ...this.get_tax_columns(with_tax_rate),
            {
                name: "Document Value",
                fieldname: GSTR1_DataField.DOC_VALUE,
                fieldtype: "Currency",
                width: 150,
            },
        ];
    }

    get_hsn_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "HSN Code",
                fieldname: GSTR1_DataField.HSN_CODE,
                width: 150,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Description",
                fieldname: GSTR1_DataField.DESCRIPTION,
                width: 300,
            },
            {
                name: "UOM",
                fieldname: GSTR1_DataField.UOM,
                width: 100,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            {
                name: "Total Quantity",
                fieldname: GSTR1_DataField.QUANTITY,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataField.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataField.CGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataField.SGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                fieldtype: "Float",
                width: 100,
            },
        ];
    }

    get_documents_issued_columns() {
        return [
            ...this.get_detail_view_column(),
            {
                name: "Document Type",
                fieldname: GSTR1_DataField.DOC_TYPE,
                width: 200,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            ...this.get_match_columns(),
            {
                name: "Sr No From",
                fieldname: GSTR1_DataField.FROM_SR,
                width: 150,
            },
            {
                name: "Sr No To",
                fieldname: GSTR1_DataField.TO_SR,
                width: 150,
            },
            {
                name: "Total Count",
                fieldname: GSTR1_DataField.TOTAL_COUNT,
                width: 120,
            },
            {
                name: "Draft Count",
                fieldname: GSTR1_DataField.DRAFT_COUNT,
                width: 120,
            },
            {
                name: "Cancelled Count",
                fieldname: GSTR1_DataField.CANCELLED_COUNT,
                width: 120,
            },
        ];
    }

    get_advances_received_columns() {
        return [
            ...this.get_detail_view_column(),
            ...this.get_match_columns(),
            ...this.get_tax_columns(true),
        ];
    }

    get_advances_adjusted_columns() {
        return [
            ...this.get_detail_view_column(),
            ...this.get_match_columns(),
            ...this.get_tax_columns(true),
        ];
    }

    // Common Columns

    get_tax_columns(with_tax_rate) {
        const columns = [
            {
                name: "Place of Supply",
                fieldname: GSTR1_DataField.POS,
                width: 150,
                _value: (...args) => this.format_detailed_table_cell(args),
            },
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataField.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CGST",
                fieldname: GSTR1_DataField.CGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "SGST",
                fieldname: GSTR1_DataField.SGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                fieldtype: "Float",
                width: 100,
            },
        ];

        if (!with_tax_rate) columns.splice(1, 1);

        return columns;
    }

    get_igst_tax_columns(with_pos) {
        const columns = [];

        if (with_pos)
            columns.push({
                name: "Place of Supply",
                fieldname: GSTR1_DataField.POS,
                width: 150,
                _value: (...args) => this.format_detailed_table_cell(args),
            });

        columns.push(
            {
                name: "Tax Rate",
                fieldname: GSTR1_DataField.TAX_RATE,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "Taxable Value",
                fieldname: GSTR1_DataField.TAXABLE_VALUE,
                fieldtype: "Float",
                width: 150,
            },
            {
                name: "IGST",
                fieldname: GSTR1_DataField.IGST,
                fieldtype: "Float",
                width: 100,
            },
            {
                name: "CESS",
                fieldname: GSTR1_DataField.CESS,
                fieldtype: "Float",
                width: 100,
            }
        );

        return columns;
    }

    get_match_columns() {
        return [];
    }

    get_detail_view_column() {
        return [];
    }
}

const is_gstr1_api_enabled = function () {
    return (
        india_compliance.is_api_enabled() &&
        !gst_settings.sandbox_mode &&
        gst_settings.enable_gstr_1_api
    );
};

const set_default_company_gstin = async function (frm) {
    frm.set_value("company_gstin", "");

    const company = frm.doc.company;
    if (!company) return;

    const { message: gstin_list } = await frappe.call(
        "india_compliance.gst_india.utils.get_gstin_list",
        { party: company }
    );

    if (gstin_list && gstin_list.length) {
        frm.set_value("company_gstin", gstin_list[0]);
    }
};

Object.assign(gstr_1, {
    GSTR1_Category,
    GSTR1_SubCategory,
    GSTR1_DataField,
    INVOICE_TYPE,
    TabManager,
    GSTR1_TabManager,
    is_gstr1_api_enabled,
    set_default_company_gstin,
});
