import {
    GSTIN_REGEX,
    REGISTERED_REGEX,
    OVERSEAS_REGEX,
    UNBODY_REGEX,
    TDS_REGEX,
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

    get_party_type(doctype) {
        return in_list(frappe.boot.sales_doctypes, doctype) ? "Customer" : "Supplier";
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

        gstin = gstin.toUpperCase();

        if (GSTIN_REGEX.test(gstin) && is_gstin_check_digit_valid(gstin)) {
            return gstin;
        }
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
