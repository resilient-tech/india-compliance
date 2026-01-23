import {
    GSTIN_REGEX,
    REGISTERED_REGEX,
    OVERSEAS_REGEX,
    UNBODY_REGEX,
    TDS_REGEX,
    TCS_REGEX,
    GST_INVOICE_NUMBER_FORMAT,
    PAN_REGEX,
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

    HSN_BIFURCATION_FROM: frappe.datetime.str_to_obj("2025-05-01"),

    get_month_year_from_period(period) {
        /**
         * Returns month or quarter and year from the period
         * Month or quarter depends on the filing frequency set in GST Settings
         *
         * @param {String} period - period in format MMYYYY
         * @returns {Array} - [month_or_quarter, year]
         */

        const month_number = period.slice(0, 2);
        const year = period.slice(2);

        return [this.MONTH[month_number - 1], year];
    },

    get_period(month_or_quarter, year) {
        /**
         * Returns the period in the format MMYYYY
         * as accepted by the GST Portal
         */

        let month;

        if (month_or_quarter.includes("-")) {
            // Quarterly
            const last_month = month_or_quarter.split("-")[1];
            const date = new Date(`${last_month} 1, ${year}`);
            month = String(date.getMonth() + 1).padStart(2, "0");
        } else {
            // Monthly
            const date = new Date(`${month_or_quarter} 1, ${year}`);
            month = String(date.getMonth() + 1).padStart(2, "0");
        }

        return `${month}${year}`;
    },

    check_duplicate_gstin(gstin, party_type, party = null) {
        if (!gstin || gstin.length !== 15) return;
        this.check_duplicate_party("gstin", gstin, party_type, party);
    },

    check_duplicate_pan(pan, party_type, party = null) {
        if (!pan || pan.length !== 10) return;
        this.check_duplicate_party("pan", pan, party_type, party);
    },

    check_duplicate_party(field, value, party_type, party = null) {
        if (!party_type) return;
        if (!frappe.boot.gst_party_types.includes(party_type)) return;

        frappe.call({
            method: "india_compliance.gst_india.utils.check_duplicate_party",
            args: { field, value, party_type, party },
        });
    },

    get_gstin_query(party, party_type = "Company", exclude_isd = false) {
        if (!party) {
            frappe.show_alert({
                message: __("Please select {0} to get GSTIN options", [__(party_type)]),
                indicator: "yellow",
            });
            return;
        }

        return {
            query: "india_compliance.gst_india.utils.get_gstin_list",
            params: { party, party_type, exclude_isd },
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

    async set_gstin_status(field, doc, force_update = false) {
        const gstin = field.value;
        if (!gstin || gstin.length !== 15) return field.set_description("");

        doc = get_doc_details(doc);

        let { message } = await frappe.call({
            method: "india_compliance.gst_india.doctype.gstin.gstin.get_gstin_status",
            args: { gstin, doc, force_update },
        });

        if (!message) message = { status: "Not Available" };

        field.set_description(
            india_compliance.get_gstin_status_desc(
                message?.status,
                message?.last_updated_on
            )
        );

        this.set_gstin_refresh_btn(field, doc);

        return message;
    },

    async set_pan_status(field, force_update = false) {
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

    validate_gst_transporter_id(transporter_id, doc) {
        if (!transporter_id || transporter_id.length !== 15) return;

        doc = get_doc_details(doc);

        frappe.call({
            method: "india_compliance.gst_india.doctype.gstin.gstin.validate_gst_transporter_id",
            args: { transporter_id, doc },
        });
    },

    get_gstin_status_desc(status, datetime) {
        if (!status) return;
        const user_date = frappe.datetime.str_to_user(datetime);
        const pretty_date = frappe.datetime.prettyDate(datetime);

        const STATUS_COLORS = {
            Active: "green",
            Cancelled: "red",
            "Not Available": "grey",
        };
        return `<div class="d-flex indicator ${STATUS_COLORS[status] || "orange"}">
                    Status:&nbsp;<strong>${status}</strong>
                    <span class="text-right ml-auto gstin-last-updated">
                        <span title="${user_date}">
                            ${datetime ? "updated " + pretty_date : ""}
                        </span>
                    </span>
                </div>`;
    },

    set_gstin_refresh_btn(field, doc) {
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
            await india_compliance.set_gstin_status(field, doc, true);
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

    validate_pan(pan) {
        if (!pan) return;

        pan = pan.trim().toUpperCase();

        if (pan.length != 10) {
            frappe.throw(__("PAN should be 10 characters long"));
        }

        if (!PAN_REGEX.test(pan)) {
            frappe.throw(__("Invalid PAN format"));
        }

        return pan;
    },

    validate_gstin(gstin, show_msg = true) {
        const opts = { title: __("Error"), indicator: "red" };

        if (!gstin || gstin.length !== 15) {
            if (show_msg) {
                frappe.msgprint({
                    message: __("GSTIN must be 15 characters long"),
                    ...opts,
                });
            }

            return;
        }

        gstin = gstin.trim().toUpperCase();

        if (GSTIN_REGEX.test(gstin) && is_gstin_check_digit_valid(gstin)) {
            return gstin;
        } else if (show_msg) {
            frappe.msgprint({
                message: __("Invalid GSTIN"),
                ...opts,
            });
        }
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
            message_list.push(
                "Transaction Name must be 16 characters or fewer to meet GST requirements"
            );
        }

        if (!GST_INVOICE_NUMBER_FORMAT.test(invoice_number)) {
            message_list.push(
                "Transaction Name should start with an alphanumeric character and can only contain alphanumeric characters, dash (-) and slash (/) to meet GST requirements."
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

    last_month_name() {
        const today = frappe.datetime.now_date(true);
        const last_month = today.getMonth() - 1;
        return this.MONTH[last_month];
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

    get_options_for_year(filing_frequency) {
        const today = new Date();
        let current_year = today.getFullYear();
        const current_month_idx = today.getMonth();
        const start_year = 2017;
        const year_range = current_year - start_year + 1;
        const options = Array.from({ length: year_range }, (_, index) =>
            (start_year + year_range - index - 1).toString()
        );

        if (
            (filing_frequency === "Monthly" && current_month_idx === 0) ||
            (filing_frequency === "Quarterly" && current_month_idx < 3)
        )
            current_year--;

        current_year = current_year.toString();
        return { options, current_year };
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

    is_e_waybill_applicable_for_subcontracting(doc) {
        if (
            !(
                gst_settings.enable_api &&
                gst_settings.enable_e_waybill &&
                gst_settings.enable_e_waybill_for_sc
            )
        ) {
            return false;
        }

        if (doc.doctype != "Stock Entry") return true;

        if (
            !["Material Transfer", "Material Issue", "Send to Subcontractor"].includes(
                doc.purpose
            )
        ) {
            return false;
        }

        return true;
    },

    is_indian_registered_company(company) {
        if (!company) return false;

        return frappe.boot.indian_registered_companies?.includes(company);
    },
});

function get_doc_details(doc) {
    return doc
        ? {
              doctype: doc.doctype,
              name: doc.name,
              docstatus: doc.docstatus,
              transaction_date: doc.posting_date || doc.transaction_date,
          }
        : null;
}

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
