frappe.provide("ic");

window.gst_settings = frappe.boot.gst_settings;
const GSTIN_REGEX = /^([0-2][0-9]|[3][0-8])[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z][A-Z0-9][Z][A-Z0-9]$/;

Object.assign(ic, {
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
        return settings.enable_api && ic.can_enable_api(settings);
    },

    is_e_invoice_enabled() {
        return ic.is_api_enabled() && gst_settings.enable_e_invoice;
    },

    validate_gstin(gstin) {
        if (!gstin || gstin.length !== 15) return;

        gstin = gstin.toUpperCase();

        if (GSTIN_REGEX.test(gstin) && is_gstin_check_digit_valid(gstin)) {
            return gstin;
        }
    }
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
