import {
    GSTIN_REGEX,
    REGISTERED_REGEX,
    OVERSEAS_REGEX,
    UNBODY_REGEX,
    TDS_REGEX,
    GST_INVOICE_NUMBER_FORMAT,
} from "./regex_constants";

frappe.provide("india_compliance");

window.gst_settings = frappe.boot.gst_settings;

Object.assign(india_compliance, {
    get_gstin_query(party, party_type = "Company") {
        if (!party) {
            frappe.show_alert({
                message: __("Please select {0} to get GSTIN options", [__(party_type)]),
                indicator: "yellow",
            });
            return;
        }

        return {
            query: "india_compliance.gst_india.utils.get_gstin_list",
            params: { party, party_type },
        };
    },

    async get_gstin_options(party, party_type = "Company") {
        const { query, params } = india_compliance.get_gstin_query(party, party_type);
        const { message } = await frappe.call({
            method: query,
            args: params,
        });
        return message;
    },

    async get_account_options(company) {
        if (!company) return;
        const { message } = await frappe.call({
            method: "india_compliance.gst_india.utils.get_all_gst_accounts",
            args: {
                company,
            },
        });

        return message || [];
    },

    get_party_type(doctype) {
        return in_list(frappe.boot.sales_doctypes, doctype) ? "Customer" : "Supplier";
    },

    async set_gstin_status(field, transaction_date, force_update = 0) {
        const gstin = field.value;
        if (!gstin || gstin.length !== 15) return field.set_description("");

        const { message } = await frappe.call({
            method: "india_compliance.gst_india.doctype.gstin.gstin.get_gstin_status",
            args: {
                gstin,
                transaction_date,
                is_request_from_ui: 1,
                force_update,
            },
        });

        if (!message) return field.set_description("");

        field.set_description(
            india_compliance.get_gstin_status_desc(
                message?.status,
                message?.last_updated_on
            )
        );

        this.set_gstin_refresh_btn(field, transaction_date);

        return message;
    },

    get_gstin_status_desc(status, datetime) {
        if (!status) return;
        const user_date = frappe.datetime.str_to_user(datetime);
        const pretty_date = frappe.datetime.prettyDate(datetime);

        const STATUS_COLORS = { Active: "green", Cancelled: "red" };
        return `<div class="d-flex indicator ${STATUS_COLORS[status] || "orange"}">
                    Status:&nbsp;<strong>${status}</strong>
                    <span class="text-right ml-auto gstin-last-updated">
                        <span title="${user_date}">
                            ${datetime ? "updated " + pretty_date : ""}
                        </span>
                    </span>
                </div>`;
    },

    set_gstin_refresh_btn(field, transaction_date) {
        if (
            !this.is_api_enabled() ||
            gst_settings.sandbox_mode ||
            !gst_settings.validate_gstin_status ||
            field.$wrapper.find(".refresh-gstin").length
        )
            return;

        const refresh_btn = $(`
            <svg class="icon icon-sm refresh-gstin" style="">
                <use class="" href="#icon-refresh" style="cursor: pointer"></use>
            </svg>
        `).appendTo(field.$wrapper.find(".gstin-last-updated"));

        refresh_btn.on("click", async function () {
            const force_update = 1;
            await india_compliance.set_gstin_status(
                field,
                transaction_date,
                force_update
            );
        });
    },

    set_state_options(frm) {
        const state_field = frm.get_field("state");
        const country = frm.get_field("country").value;
        if (country !== "India") {
            state_field.set_data([]);
            return;
        }

        state_field.set_data(frappe.boot.india_state_options || []);
    },

    can_enable_api(settings) {
        return settings.api_secret || frappe.boot.ic_api_enabled_from_conf;
    },

    is_api_enabled(settings) {
        if (!settings) settings = gst_settings;
        return settings.enable_api && india_compliance.can_enable_api(settings);
    },

    is_e_invoice_enabled() {
        return india_compliance.is_api_enabled() && gst_settings.enable_e_invoice;
    },

    validate_gstin(gstin) {
        if (!gstin || gstin.length !== 15) return;

        gstin = gstin.trim().toUpperCase();

        if (GSTIN_REGEX.test(gstin) && is_gstin_check_digit_valid(gstin)) {
            return gstin;
        }
    },

    get_gstin_otp(error_type, company_gstin) {
        let description =
            "An OTP has been sent to your registered mobile/email for further authentication. Please provide OTP.";
        if (error_type === "invalid_otp")
            description = "Invalid OTP was provided. Please try again.";

        return new Promise(resolve => {
            const prompt = new frappe.ui.Dialog({
                title: __("Enter OTP"),
                fields: [
                    {
                        fieldtype: "Data",
                        label: __("One Time Password"),
                        fieldname: "otp",
                        reqd: 1,
                        description: description,
                    },
                ],
                primary_action_label: __("Submit"),
                primary_action(values) {
                    resolve(values.otp);
                    prompt.hide();
                },
                secondary_action_label: __("Resend OTP"),
                secondary_action() {
                    frappe.call({
                        method: "india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool.resend_otp",
                        args: { company_gstin },
                        callback: function () {
                            frappe.show_alert({
                                message: __("OTP has been resent."),
                                indicator: "green",
                            });
                            prompt.get_secondary_btn().addClass("disabled");
                        },
                    });
                },
            });
            prompt.show();
        });
    },

    guess_gst_category(gstin, country) {
        if (!gstin) {
            if (country && country !== "India") return "Overseas";
            return "Unregistered";
        }

        if (TDS_REGEX.test(gstin)) return "Tax Deductor";
        if (REGISTERED_REGEX.test(gstin)) return "Registered Regular";
        if (UNBODY_REGEX.test(gstin)) return "UIN Holders";
        if (OVERSEAS_REGEX.test(gstin)) return "Overseas";
    },

    set_hsn_code_query(field) {
        if (!field || !gst_settings.validate_hsn_code) return;
        field.get_query = function () {
            const wildcard = "_".repeat(gst_settings.min_hsn_digits) + "%";
            return {
                filters: {
                    name: ["like", wildcard],
                },
            };
        };
    },

    set_reconciliation_status(frm, field) {
        if (!frm.doc.docstatus === 1 || !frm.doc.reconciliation_status) return;

        const STATUS_COLORS = {
            Reconciled: "green",
            Unreconciled: "red",
            Ignored: "grey",
            "Not Applicable": "grey",
        };
        const color = STATUS_COLORS[frm.doc.reconciliation_status];

        frm.get_field(field).set_description(
            `<div class="d-flex indicator ${color}">
                2A/2B Status:&nbsp;<strong>${frm.doc.reconciliation_status}</strong>
            </div>`
        );
    },

    validate_invoice_number(invoice_number) {
        if (invoice_number.length > 16) {
            frappe.throw(
                __("GST Invoice Number cannot exceed 16 characters"),
                __("Invalid GST Invoice Number")
            );
        }

        if (!GST_INVOICE_NUMBER_FORMAT.test(invoice_number)) {
            frappe.throw(
                __(
                    "GST Invoice Number should start with an alphanumeric character and can only contain alphanumeric characters, dash (-) and slash (/)"
                ),
                __("Invalid GST Invoice Number")
            );
        }
    },

    trigger_file_download(file_content, file_name) {
        let type = "application/json;charset=utf-8";

        if (!file_name.endsWith(".json")) {
            type = "application/octet-stream";
        }
        const blob = new Blob([file_content], { type: type });

        // Create a link and set the URL using `createObjectURL`
        const link = document.createElement("a");
        link.style.display = "none";
        link.href = URL.createObjectURL(blob);
        link.download = file_name;

        // It needs to be added to the DOM so it can be clicked
        document.body.appendChild(link);
        link.click();

        // To make this work on Firefox we need to wait
        // a little while before removing it.
        setTimeout(() => {
            URL.revokeObjectURL(link.href);
            link.parentNode.removeChild(link);
        }, 0);
    },

    set_last_month_as_default_period(report) {
        report.filters.forEach(filter => {
            if (filter.fieldname === "from_date") {
                filter.default = this.last_month_start();
            }
            if (filter.fieldname === "to_date") {
                filter.default = this.last_month_end();
            }
        });
    },

    last_month_start() {
        return frappe.datetime.add_months(frappe.datetime.month_start(), -1);
    },

    last_month_end() {
        return frappe.datetime.add_days(frappe.datetime.month_start(), -1);
    },

    primary_to_danger_btn(parent) {
        parent.$wrapper
            .find(".btn-primary")
            .removeClass("btn-primary")
            .addClass("btn-danger");
    },

    add_divider_to_btn_group(btn_group_name) {
        $(document)
            .find(`.inner-group-button[data-label=${btn_group_name}]`)
            .find(`.dropdown-menu`)
            .append($('<li class="dropdown-divider"></li>'));
    },

    make_text_red(btn_group_name, btn_name) {
        $(document)
            .find(`.inner-group-button[data-label=${btn_group_name}]`)
            .find(`.dropdown-item[data-label="${encodeURIComponent(btn_name)}"]`)
            .addClass("text-danger");
    },
});

function is_gstin_check_digit_valid(gstin) {
    /*
    adapted from
    https://gitlab.com/srikanthlogic/gstin-validator/-/blob/master/src/index.js
    */

    const GSTIN_CODEPOINT_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const mod = GSTIN_CODEPOINT_CHARS.length;

    let factor = 2;
    let sum = 0;

    for (let i = gstin.length - 2; i >= 0; i--) {
        let codePoint = -1;
        for (let j = 0; j < GSTIN_CODEPOINT_CHARS.length; j++) {
            if (GSTIN_CODEPOINT_CHARS[j] === gstin[i]) {
                codePoint = j;
            }
        }
        let digit = factor * codePoint;
        factor = factor === 2 ? 1 : 2;
        digit = Math.floor(digit / mod) + (digit % mod);
        sum += digit;
    }

    const checkCodePoint = (mod - (sum % mod)) % mod;
    return GSTIN_CODEPOINT_CHARS[checkCodePoint] === gstin[14];
}

// Will be deprecated after v15 release, kept only for compatibility
// DO NOT USE IN CODE
window.ic = window.india_compliance;
