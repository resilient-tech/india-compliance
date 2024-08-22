import {
    GSTIN_REGEX,
    REGISTERED_REGEX,
    OVERSEAS_REGEX,
    UNBODY_REGEX,
    TDS_REGEX,
    TCS_REGEX,
    GST_INVOICE_NUMBER_FORMAT,
} from "./regex_constants";

frappe.provide("india_compliance");

window.gst_settings = frappe.boot.gst_settings;

Object.assign(india_compliance, {
    MONTH: [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],

    QUARTER: ["Jan-Mar", "Apr-Jun", "Jul-Sep", "Oct-Dec"],

    get_month_year_from_period(period) {
        /**
         * Returns month or quarter and year from the period
         * Month or quarter depends on the filing frequency set in GST Settings
         *
         * @param {String} period - period in format MMYYYY
         * @returns {Array} - [month_or_quarter, year]
         */

        const { filing_frequency } = gst_settings;
        const month_number = period.slice(0, 2);
        const year = period.slice(2);

        if (filing_frequency === "Monthly") return [this.MONTH[month_number - 1], year];
        else return [this.QUARTER[Math.floor(month_number / 3)], year];
    },

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

    async set_gstin_status(field, transaction_date, force_update) {
        const gstin = field.value;
        if (!gstin || gstin.length !== 15) return field.set_description("");

        const { message } = await frappe.call({
            method: "india_compliance.gst_india.doctype.gstin.gstin.get_gstin_status",
            args: { gstin, transaction_date, force_update },
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

    async set_pan_status(field, force_update = null) {
        const pan = field.value;
        field.set_description("");
        if (!pan || pan.length !== 10) return;

        let { message } = await frappe.call({
            method: "india_compliance.gst_india.doctype.pan.pan.get_pan_status",
            args: { pan, force_update },
        });

        if (!message) return;

        const [pan_status, datetime] = message;
        const STATUS_COLORS = {
            Valid: "green",
            "Not Linked": "red",
            Invalid: "red",
        };

        const user_date = frappe.datetime.str_to_user(datetime);
        const pretty_date = frappe.datetime.prettyDate(datetime);
        const pan_desc = $(
            `<div class="d-flex indicator ${STATUS_COLORS[pan_status] || "orange"}">
                Status:&nbsp;<strong>${pan_status}</strong>
                <span class="text-right ml-auto">
                    <span title="${user_date}">
                        ${datetime ? "updated " + pretty_date : ""}
                    </span>
                    <svg class="icon icon-sm refresh-pan" style="cursor: pointer;">
                        <use href="#icon-refresh"></use>
                    </svg>
                </span>
            </div>`
        );

        pan_desc.find(".refresh-pan").on("click", async function () {
            await india_compliance.set_pan_status(field, true);
        });
        return field.set_description(pan_desc);
    },

    validate_gst_transporter_id(transporter_id) {
        if (!transporter_id || transporter_id.length !== 15) return;

        frappe.call({
            method: "india_compliance.gst_india.doctype.gstin.gstin.validate_gst_transporter_id",
            args: { transporter_id },
        });
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
            const force_update = true;
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
        if (!gstin || gstin.length !== 15) {
            frappe.msgprint(__("GSTIN must be 15 characters long"));
            return;
        }

        gstin = gstin.trim().toUpperCase();

        if (GSTIN_REGEX.test(gstin) && is_gstin_check_digit_valid(gstin)) {
            return gstin;
        } else {
            frappe.msgprint(__("Invalid GSTIN"));
        }
    },

    get_gstin_otp(company_gstin, error_type) {
        let description = `An OTP has been sent to the registered mobile/email for GSTIN ${company_gstin} for further authentication. Please provide OTP.`;
        if (error_type === "invalid_otp")
            description = `Invalid OTP was provided for GSTIN ${company_gstin}. Please try again.`;

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
                        method: "india_compliance.gst_india.utils.gstr_utils.request_otp",
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
        if (TCS_REGEX.test(gstin)) return "Tax Collector";
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
            "Match Found": "yellow",
        };
        const color = STATUS_COLORS[frm.doc.reconciliation_status];

        frm.get_field(field).set_description(
            `<div class="d-flex indicator ${color}">
                2A/2B Status:&nbsp;<strong>${frm.doc.reconciliation_status}</strong>
            </div>`
        );
    },

    validate_invoice_number(invoice_number) {
        // returns a list of error messages if invoice number is invalid
        let message_list = [];
        if (invoice_number.length > 16) {
            message_list.push("GST Invoice Number cannot exceed 16 characters");
        }

        if (!GST_INVOICE_NUMBER_FORMAT.test(invoice_number)) {
            message_list.push(
                "GST Invoice Number should start with an alphanumeric character and can only contain alphanumeric characters, dash (-) and slash (/)."
            );
        }

        return message_list;
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

    last_half_year(position) {
        const today = frappe.datetime.now_date(true);
        const current_month = today.getMonth() + 1;
        const current_year = today.getFullYear();

        if (current_month <= 3) {
            return position === "start"
                ? `${current_year - 1}-03-01`
                : `${current_year - 1}-09-30`;

        } else if (current_month <= 9) {
            return position === "start"
                ? `${current_year - 1}-10-01`
                : `${current_year}-03-31`;

        } else {
            return position === "start"
                ? `${current_year}-04-01`
                : `${current_year}-09-30`;
        }
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

    async authenticate_company_gstins(company, company_gstin) {
        const { message: gstin_authentication_status } = await frappe.call({
            method: "india_compliance.gst_india.utils.gstr_utils.validate_company_gstins",
            args: { company: company, company_gstin: company_gstin },
        });

        for (let gstin of Object.keys(gstin_authentication_status)) {
            if (gstin_authentication_status[gstin]) continue;

            gstin_authentication_status[gstin] =
                await this.request_and_authenticate_otp(gstin);
        }

        return Object.keys(gstin_authentication_status);
    },

    async request_and_authenticate_otp(gstin) {
        await frappe.call({
            method: "india_compliance.gst_india.utils.gstr_utils.request_otp",
            args: { company_gstin: gstin },
        });

        // wait for OTP to be authenticated to proceed
        await this.authenticate_otp(gstin);
    },

    async authenticate_otp(gstin, error_type = null) {
        if (!error_type) error_type = "otp_requested";

        let is_authenticated = false;

        while (!is_authenticated) {
            const otp = await this.get_gstin_otp(gstin, error_type);

            const { message } = await frappe.call({
                method: "india_compliance.gst_india.utils.gstr_utils.authenticate_otp",
                args: { company_gstin: gstin, otp: otp },
            });

            if (
                message &&
                ["otp_requested", "invalid_otp"].includes(message.error_type)
            ) {
                error_type = message.error_type;
                continue;
            }

            is_authenticated = true;
            return true;
        }
    },

    show_dismissable_alert(wrapper, message, alert_type = "primary", on_close = null) {
        const alert = $(`
            <div class="container">
            <div
                class="alert alert-${alert_type} alert-dismissable fade show d-flex justify-content-between border-0"
                role="alert"
            >
                <div>${message}</div>
                <button
                    type="button"
                    class="close"
                    data-dismiss="alert"
                    aria-label="Close"
                    style="outline: 0px solid black !important"
                >
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
            </div>
        `).prependTo(wrapper);

        alert.on("closed.bs.alert", () => {
            if (on_close) on_close();
        });

        return alert;
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
