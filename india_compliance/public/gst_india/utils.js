frappe.provide("ic");

ic.get_gstin_query = company => {
    if (!company) {
        frappe.show_alert({
            message: __("Please select Company to get GSTIN options"),
            indicator: "yellow",
        });
        return;
    }

    return {
        query: "india_compliance.gst_india.utils.get_gstin_list",
        params: {
            party: company,
        },
    };
};

ic.get_party_type = function (doctype) {
    return in_list(frappe.boot.sales_doctypes, doctype) ? "Customer" : "Supplier";
};

ic.set_state_options = function (frm) {
    const state_field = frm.get_field("state");
    const country = frm.get_field("country").value;
    if (country !== "India") {
        state_field.set_data([]);
        return;
    }

    state_field.set_data(frappe.boot.india_state_options || []);
};

ic.gstin_doctypes = ["Customer", "Supplier", "Company"];

ic.can_enable_api = function (gst_settings) {
    return Boolean(gst_settings.api_secret || frappe.boot.ic_api_enabled);
};

ic.is_api_enabled = function () {
    frappe.db.get_doc("GST Settings", "GST Settings").then(gst_settings => {
        return (ic.can_enable_api(gst_settings) || gst_settings.enable_api) ? true : false;
    })
};
