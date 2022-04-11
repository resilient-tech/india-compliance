frappe.provide("ic.utils");

ic.get_gstin_query = company => {
    if (!company) {
        frappe.show_alert({
            message: __("Please select Company to get GSTIN options"),
            indicator: "yellow",
        });
        return;
    }

    return {
        query: "india_compliance.gst_india.utils.queries.get_gstin_options",
        params: {
            company: company,
        },
    };
};

ic.utils.get_party_type = function (doctype) {
    return in_list(
        ["Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "POS Invoice"],
        doctype
    )
        ? "Customer"
        : "Supplier";
};

export async function autofill_gstin_fields(frm) {
    const gstin = frm.doc._gstin || frm.doc.gstin;
    if (!gstin || gstin.length != 15) return;

    const gstin_info = await get_gstin_details(gstin);
    map_gstin_details(frm.doc, gstin_info);
    frm.refresh();

    setup_pincode_field(frm, gstin_info);
}

function setup_pincode_field(frm, gstin_info) {
    const pincode_field = frm.fields_dict._pincode;
    pincode_field.set_data(
        gstin_info.all_addresses.map(address => {
            return {
                label: address.pincode,
                value: address.pincode,
                description: `${address.address_line1}, ${address.address_line2}, ${address.city}, ${address.state}`,
            };
        })
    );

    pincode_field.df.onchange = _ => {
        autofill_address(frm.doc, gstin_info);
        frm.refresh();
    };
}

function get_gstin_details(gstin) {
    return frappe
        .call({
            method: "india_compliance.gst_india.utils.get_gstin_details",
            args: { gstin },
        })
        .then(r => r.message);
}

function map_gstin_details(doc, gstin_info) {
    if (!gstin_info) return;
    if (gstin_info.permanent_address)
        update_address_info(doc, gstin_info.permanent_address);
    update_party_info(doc, gstin_info);
}

function update_party_info(doc, gstin_info) {
    doc.gstin = doc._gstin;
    doc.supplier_name = doc.customer_name = gstin_info.business_name;
    doc.gst_category = gstin_info.gst_category;
}

function update_address_info(doc, address) {
    if (!address || doc.address_line1 === address.address_line1) return;

    Object.assign(doc, address);

    // renamed address_line1 to stop execution of erpnext.selling.doctype.customer.customer.create_primary_address
    doc._address_line1 = doc.address_line1;
    delete doc.address_line1;

    doc.pincode = doc._pincode = address.pincode;
}

function autofill_address(doc, { all_addresses }) {
    const { _pincode: pincode } = doc;
    if (!pincode || pincode.length !== 6 || !all_addresses) return;
    update_address_info(
        doc,
        all_addresses.find(address => address.pincode == pincode)
    );
}
