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
    },

});
