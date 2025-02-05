// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

const GSTIN_FIELDNAME = [
    "status",
    "registration_date",
    "last_updated_on",
    "cancelled_date",
    "is_blocked",
];

frappe.query_reports["GSTIN Status"] = {
    html_enabled: true,

    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: [
                "",
                "Active",
                "Cancelled",
                "Inactive",
                "Provisional",
                "Suspended",
            ],
        },
        {
            fieldname: "party_type",
            label: __("Party Type"),
            fieldtype: "Select",
            options: ["", "Customer", "Supplier"],
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        if (data) {
            if (column.fieldname == "status") {
                value = get_colored_status(value);
            } else if (column.fieldname == "update_gstin_details_btn") {
                value = create_btn_with_gstin_attr(data.gstin);
            } else {
                if (column.fieldname == "last_updated_on") {
                    value = frappe.datetime.prettyDate(value);
                } else {
                    value = default_formatter(value, row, column, data);
                }
                value = `<span fieldname="${column.fieldname}">${value}</span>`;
            }
        }

        return value;
    },

    add_on_click_listner(gstin) {
        toggle_gstin_update_btn(gstin, (disabled = true));
        const affectedElements = $(`div.dt-cell__content[title='${gstin}']`);
        set_btn_text(gstin, "Updating");

        frappe.call({
            method: "india_compliance.gst_india.doctype.gstin.gstin.get_gstin_status",
            args: {
                gstin: gstin,
                force_update: true,
            },
            callback: function (r) {
                if (r.message) {
                    let data = r.message;
                    affectedElements.each(function () {
                        row = this.parentElement.attributes["data-row-index"].value;
                        for (let fieldname of GSTIN_FIELDNAME) {
                            update_value(row, fieldname, data[fieldname]);
                        }
                    });
                    set_btn_text(gstin, "Updated");
                } else {
                    toggle_gstin_update_btn(gstin, (disabled = false));
                }
            },
        });
    },

    get_datatable_options(datatable_options) {
        datatable_options.cellHeight = 35;

        return datatable_options;
    },
};
const STATUS_TO_COLOR_MAPPING = {
    Active: "green",
    Cancelled: "red",
    Inactive: "black",
    Provisional: "black",
    Suspended: "black",
};

function get_colored_status(status) {
    if (!status) return "";
    return `<div style="color: ${STATUS_TO_COLOR_MAPPING[status]}; text-align:center; width:100%;">${status}</div>`;
}

function set_btn_text(gstin, text) {
    let btn = $(`button[data-gstin='${gstin}']`);
    btn.text(text);
}

function toggle_gstin_update_btn(gstin, disabled = null) {
    let btn = $(`button[data-gstin='${gstin}']`);
    if (disabled == null) {
        disabled = btn.prop("disabled");
        disabled = !disabled;
    }

    btn.prop("disabled", disabled);
}

function create_btn_with_gstin_attr(gstin) {
    const BUTTON_HTML = `<button
		data-fieldname="gstin_update_btn"
		class="btn btn-xs btn-primary center"
		data-gstin="${gstin}"
		onclick="frappe.query_reports['GSTIN Status'].add_on_click_listner('${gstin}')"
	>
		Update
	</button>`;

    return BUTTON_HTML;
}

function update_value(row, fieldname, value) {
    let ele = $(`.dt-row.dt-row-${row}.vrow > div > div > [fieldname='${fieldname}']`);

    let column = frappe.query_report.columns.find(column => {
        return column.fieldname == fieldname;
    });
    fieldtype = column.fieldtype;

    if (fieldname == "is_blocked") {
        value = [undefined, null].includes(value) ? "" : value == 0 ? "No" : "Yes";
    } else if (fieldname == "last_updated_on") {
        value = frappe.datetime.prettyDate(value);
    } else {
        const formatter = frappe.form.get_formatter(fieldtype);
        value = formatter(value);
    }

    ele.text(value);
    ele.parent().attr("title", value);
}
