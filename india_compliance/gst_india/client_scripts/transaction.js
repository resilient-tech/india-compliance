// functions in this file will apply to most transactions
// POS Invoice is a notable exception since it doesn't get created from the UI

function setup_auto_gst_taxation(doctype) {
    const events = Object.fromEntries(
        [
            "company_address",
            "shipping_address",
            "customer_address",
            "supplier_address",
            "tax_category",
        ].map(field => [field, get_tax_template])
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
        party_fields.map(field => [field, frm.doc[field]])
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

function fetch_gst_category(doctype) {
    const party_type = ic.get_party_type(doctype);
    const party_type_field = party_type.toLowerCase();
    frappe.ui.form.on(doctype, {
        setup(frm) {
            // set gst category from party first, can be overwritten from address
            frm.add_fetch(party_type_field, "gst_category", "gst_category");
        },
    });
}

function validate_overseas_gst_category(doctype) {
    frappe.ui.form.on(doctype, {
        gst_category(frm) {
            const { enable_overseas_transactions } = frappe.boot.gst_settings;
            if (
                !["SEZ", "Overseas"].includes(frm.doc.gst_category) ||
                enable_overseas_transactions
            )
                return;

            frappe.throw(
                __("Please enable SEZ / Overseas transactions in GST Settings first")
            );
        },
    });
}
