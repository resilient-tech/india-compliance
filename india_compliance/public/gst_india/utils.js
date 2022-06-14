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
    return in_list(
        [
            "Material Request",
            "Request for Quotation",
            "Supplier Quotation",
            "Purchase Order",
            "Purchase Receipt",
            "Purchase Invoice",
        ],
        doctype
    )
        ? "Supplier"
        : "Customer";
};

ic.set_state_options = function (state_field, country) {
    console.log(state_field, country);

    if (country !== "India") {
        state_field.set_data([]);
        return;
    }

    state_field.set_data(frappe.boot.india_state_value || []);
}
