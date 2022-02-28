frappe.provide("india_compliance.utils");

// GSTIN Validation
// taken from: gitlab.com/srikanthlogic/gstin -validator/-/blob/master/src/index.js

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

india_compliance.utils.validate_gst_number = isValidGSTNumber;
window.validate_gst_number = india_compliance.utils.validate_gst_number;
