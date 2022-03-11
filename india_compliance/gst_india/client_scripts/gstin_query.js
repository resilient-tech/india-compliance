function get_gstin_query(company) {
    if (!company) {
        frappe.show_alert({
            message: __("Please select Company to get GSTIN options"),
            indicator: "yellow",
        });

        return;
    }

    return {
        query: 'india_compliance.gst_india.utils.queries.get_gstin_options',
        params: {
            company: company,
        }
    }
}
