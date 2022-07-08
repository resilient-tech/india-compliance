frappe.provide("ic");

ic.get_gstin_query_for_company = company => {
    if (!company) {
        frappe.show_alert({
            message: __("Please select Company to get GSTIN options"),
            indicator: "yellow",
        });
        return;
    }

    return ic.get_gstin_query(company, "Company");
};

ic.get_gstin_query = function (party, party_type) {
    return {
        query: "india_compliance.gst_india.utils.get_gstin_list",
        params: { party, party_type },
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
