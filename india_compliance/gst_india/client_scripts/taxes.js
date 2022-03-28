function setup_auto_gst_taxation(doctype) {
    const events = Object.fromEntries(
        [
            "company_address",
            "shipping_address",
            "customer_address",
            "supplier_address",
            "tax_category",
        ].map((field) => [field, get_tax_template])
    );

    frappe.ui.form.on(doctype, events);
}

function get_tax_template(frm) {
    if (!frm.doc.company) return;

    const party_fields = [
        "shipping_address",
        "customer_address",
        "supplier_address",
        "shipping_address_name",
        "customer",
        "supplier",
        "supplier_gstin",
        "company_gstin",
        "tax_category",
    ];

    const party_details = Object.fromEntries(
        party_fields.map((field) => [field, frm.doc[field]])
    );

    frappe.call({
        method: "india_compliance.gst_india.overrides.transaction.get_regional_address_details",
        args: {
            party_details: JSON.stringify(party_details),
            doctype: frm.doc.doctype,
            company: frm.doc.company,
        },
        debounce: 2000,
        callback(r) {
            if (r.message) {
                frm.set_value("taxes_and_charges", r.message.taxes_and_charges);
                frm.set_value("taxes", r.message.taxes);
                frm.set_value("place_of_supply", r.message.place_of_supply);
            }
        },
    });
}

function fetch_and_highlight_gst_category(doctype) {
    const party_type = get_party_type(doctype);

    let events = {
        setup(frm) {
            // set gst category from party first, can be overwritten from address
            frm.add_fetch(party_type, "gst_category", "gst_category");
        },
        refresh: _highlight_gst_category,
        gst_category: _highlight_gst_category,
    };
    frappe.ui.form.on(doctype, events);
}

function _highlight_gst_category(frm) {
    const party_type = get_party_type(frm.doctype);
    const party_field = frm.fields_dict[party_type];

    if (!frm.doc[party_type] || !frm.doc.gst_category) {
        party_field.set_description("");
        return;
    }

    party_field.set_description(`<em>${frm.doc.gst_category}</em>`);
}

function get_party_type(doctype) {
    return in_list(
        [
            "Quotation",
            "Sales Order",
            "Delivery Note",
            "Sales Invoice",
            "POS Invoice",
        ],
        doctype
    )
        ? "customer"
        : "supplier";
}
