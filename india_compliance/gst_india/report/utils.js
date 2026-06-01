const INWARD_SECTION_MAPPING = {
    4: {
        "ITC Available": [
            "Import Of Goods",
            "Import Of Service",
            "ITC on Reverse Charge",
            "Input Service Distributor",
            "All Other ITC",
        ],
        "ITC Reversed": ["As per rules 42 & 43 of CGST Rules and section 17(5)", "Others"],
        "Ineligible ITC": ["Reclaim of ITC Reversal", "ITC restricted due to PoS rules"],
    },
    5: {
        "Composition Scheme, Exempted, Nil Rated": ["Composition Scheme, Exempted, Nil Rated"],
        "Non-GST": ["Non-GST"],
    },
};

function get_inward_subcategory_options(sub_section) {
    return Object.values(INWARD_SECTION_MAPPING[sub_section] || {}).flat();
}

function fetch_gstins(report) {
    const company = report.get_filter_value("company");
    const gstin_field = report.get_filter("company_gstin");

    if (!company) {
        gstin_field.df.options = [""];
        gstin_field.refresh();
        return;
    }

    frappe.call({
        method: "india_compliance.gst_india.utils.get_gstin_list",
        async: false,
        args: {
            party: company,
        },
        callback(r) {
            r.message.unshift("");
            gstin_field.df.options = r.message;
            gstin_field.refresh();
        },
    });
}
