// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

const GSTIN_FIELDNAME = [
    "status",
    "registration_date",
    "last_updated_on",
    "cancelled_date",
    "is_blocked",
];

frappe.query_reports["GSTIN Detailed"] = {
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
            value = default_formatter(value, row, column, data);

            if (column.fieldname == "status") {
                value = get_colored_status(value);
            } else if (column.fieldname == "update_gstin_details_btn") {
                value = create_btn_with_gstin_attr(data.gstin);
            } else {
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
};
const STATUS_TO_COLOR_MAPPING = {
    Active: "green", // Green with 70% opacity
    Cancelled: "red", // Red with 70% opacity
    Inactive: "orange", // Orange with 70% opacity
    Provisional: "yellow", // Yellow with 70% opacity
    Suspended: "grey", // Grey with 70% opacity
};

function get_colored_status(status) {
    return `<span class="badge" style="
        background-color: ${STATUS_TO_COLOR_MAPPING[status]};
        color: white;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        padding: 6px 12px;
        display: inline-block;
        backdrop-filter: blur(5px);
		opacity: 0.7;
    ">${status}</span>`;
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
		onclick="frappe.query_reports['GSTIN Detailed'].add_on_click_listner('${gstin}')"
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

    const formatter = frappe.form.get_formatter(fieldtype);
    value = formatter(value);

    if (fieldname == "is_blocked") {
        value = [undefined, null].includes(value) ? "" : value == 0 ? "No" : "Yes";
    }

    ele.text(value);
    ele.parent().attr("title", value);
}
