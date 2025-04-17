// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

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

    get_datatable_options(datatable_options) {
        datatable_options.cellHeight = 35;
        return datatable_options;
    },

    formatter: function (value, row, column, data, default_formatter) {
        if (!data) return value;

        const { fieldname } = column;

        if (fieldname == "status") {
            value = this.get_colored_status(value);
        } else if (fieldname == "update_gstin_details_btn") {
            value = this.get_btn_with_attr(data);
        } else {
            if (fieldname == "last_updated_on") {
                value = frappe.datetime.prettyDate(value);
            } else {
                value = default_formatter(value, row, column, data);
            }
            value = `<span fieldname="${fieldname}">${value}</span>`;
        }

        return value;
    },

    STATUS_TO_COLOR_MAPPING: {
        Active: "green",
        Cancelled: "red",
        Inactive: "black",
        Provisional: "black",
        Suspended: "black",
    },

    get_colored_status(status) {
        return `<span
            style="color: ${
                this.STATUS_TO_COLOR_MAPPING[status]
            }; text-align:center; width:100%;"
            fieldname="status"
        >
            ${frappe.utils.escape_html(status)}
        </span>`;
    },

    get_btn_with_attr(data) {
        const BUTTON_HTML = `<button
            fieldname="update_gstin_details_btn"
            class="btn btn-xs btn-primary center"
            data-gstin="${data.gstin}"
            data-party-type="${data.party_type}"
            data-party="${data.party}"

        >
            ${__("Update")}
        </button>`;

        return BUTTON_HTML;
    },

    onload() {
        $(document).on(
            "click",
            "button[fieldname='update_gstin_details_btn']",
            async e => {
                await this.handle_click_listner(e);
            }
        );
    },

    async handle_click_listner(e) {
        const gstin = e.target.attributes["data-gstin"].value;

        this.toggle_gstin_update_btn(gstin, (disabled = true));
        this.set_btn_text(gstin, __("Updating"));

        try {
            const { message } = await frappe.call({
                method: "india_compliance.gst_india.doctype.gstin.gstin.get_gstin_status",
                args: {
                    gstin: gstin,
                    force_update: true,
                    doc: {
                        doctype: e.target.attributes["data-party-type"].value,
                        name: e.target.attributes["data-party"].value,
                    },
                },
            });

            if (message) {
                this.update_gstin_values(gstin, message);
                this.set_btn_text(gstin, __("Updated"));
            } else {
                throw new Error("Invalid Response");
            }
        } catch (error) {
            frappe.show_alert({
                message: __(
                    "Error while updating GSTIN status. Please try again later."
                ),
                indicator: "red",
            });
            this.toggle_gstin_update_btn(gstin, (disabled = false));
            this.set_btn_text(gstin, __("Update"));
        }
    },

    toggle_gstin_update_btn(gstin, disabled = null) {
        let btn = $(
            `button[fieldname='update_gstin_details_btn'][data-gstin='${gstin}']`
        );
        if (disabled == null) {
            disabled = btn.prop("disabled");
            disabled = !disabled;
        }

        btn.prop("disabled", disabled);
    },

    set_btn_text(gstin, text) {
        let btn = $(`button[data-gstin='${gstin}']`);
        btn.text(frappe.utils.escape_html(text));
    },

    GSTIN_FIELDNAME: [
        "status",
        "registration_date",
        "last_updated_on",
        "cancelled_date",
        "is_blocked",
    ],

    update_gstin_values(gstin, data) {
        const affectedElements = $(`div.dt-cell__content[title='${gstin}']`);

        affectedElements.each((_, ele) => {
            let row = ele.parentElement.attributes["data-row-index"].value;
            for (let fieldname of this.GSTIN_FIELDNAME) {
                this.update_value(row, fieldname, data[fieldname]);
            }
        });
    },

    update_value(row, fieldname, value) {
        const ele = $(
            `.dt-row.dt-row-${row}.vrow > div > div > [fieldname='${fieldname}']`
        );
        let { fieldtype } = frappe.query_report.columns.find(column => {
            return column.fieldname == fieldname;
        });
        let formatter;
        switch (fieldname) {
            case "is_blocked":
                value = [undefined, null].includes(value)
                    ? ""
                    : value === 0
                    ? "No"
                    : "Yes";
                break;
            case "status":
                ele.css("color", this.STATUS_TO_COLOR_MAPPING[value]);
                break;
            case "last_updated_on":
                value = frappe.datetime.prettyDate(value);
                break;
            default:
                formatter = frappe.form.get_formatter(fieldtype);
                value = formatter(value);
        }

        ele.text(value);
        ele.parent().attr("title", value);
    },
};
