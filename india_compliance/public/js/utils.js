
window.gst_settings = frappe.boot.gst_settings;

frappe.provide("ic");

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
    }
});



frappe.provide("ic.utils");

// GSTIN Validation
// taken from: https://gitlab.com/srikanthlogic/gstin-validator/-/blob/master/src/index.js

function calcCheckSum(gstin) {
    var GSTN_CODEPOINT_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    var factor = 2;
    var sum = 0;
    var checkCodePoint = 0;
    var mod = GSTN_CODEPOINT_CHARS.length;
    var i;

    for (i = gstin.length - 2; i >= 0; i--) {
        var codePoint = -1;
        for (var j = 0; j < GSTN_CODEPOINT_CHARS.length; j++) {
            if (GSTN_CODEPOINT_CHARS[j] === gstin[i]) {
                codePoint = j;
            }
        }
        var digit = factor * codePoint;
        factor = factor === 2 ? 1 : 2;
        digit = Math.floor(digit / mod) + (digit % mod);
        sum += digit;
    }
    checkCodePoint = (mod - (sum % mod)) % mod;
    return GSTN_CODEPOINT_CHARS[checkCodePoint];
}

// GSTIN Regex validation result
function validatePattern(gstin) {
    // eslint-disable-next-line max-len
    var gstinRegexPattern =
        /^([0-2][0-9]|[3][0-8])[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z][A-Z0-9][Z][A-Z0-9]$/;
    return gstinRegexPattern.test(gstin);
}

function isValidGSTNumber(gstin) {
    gstin = gstin.toUpperCase();
    if (gstin.length !== 15) {
        return false;
    }
    if (validatePattern(gstin)) {
        return gstin[14] === calcCheckSum(gstin.toUpperCase());
    }
    return false;
}

window.validate_gst_number = ic.utils.validate_gst_number = isValidGSTNumber;


