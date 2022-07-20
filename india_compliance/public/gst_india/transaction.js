// functions in this file will apply to most transactions
// POS Invoice is a notable exception since it doesn't get created from the UI

const TRANSACTION_DOCTYPES = [
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
];

for (const doctype of TRANSACTION_DOCTYPES) {
    fetch_gst_details(doctype);
    validate_overseas_gst_category(doctype);
}

function fetch_gst_details(doctype) {
    const event_fields = ["tax_category", "company_gstin"];

    // we are using address below to prevent multiple event triggers
    if (in_list(frappe.boot.sales_doctypes, doctype)) {
        event_fields.push(
            "customer_address",
            "is_export_with_gst",
            "is_reverse_charge"
        );
    } else {
        event_fields.push("supplier_address");
    }

    const events = Object.fromEntries(
        event_fields.map(field => [field, update_gst_details])
    );

    frappe.ui.form.on(doctype, events);
}

async function update_gst_details(frm) {
    if (frm.__gst_update_triggered || frm.updating_party_details || !frm.doc.company) return;

    const party_type = ic.get_party_type(frm.doc.doctype).toLowerCase();
    if (!frm.doc[party_type]) return;

    frm.__gst_update_triggered = true;
    // wait for GSTINs to get fetched
    await frappe.after_ajax().then(() => frm.__gst_update_triggered = false);

    const party_fields = ["tax_category", "gst_category", "company_gstin", party_type];

    if (in_list(frappe.boot.sales_doctypes, frm.doc.doctype)) {
        party_fields.push(
            "customer_address",
            "billing_address_gstin",
            "is_export_with_gst",
            "is_reverse_charge"
        );
    } else {
        party_fields.push("supplier_address", "supplier_gstin");
    }

    const party_details = Object.fromEntries(
        party_fields.map(field => [field, frm.doc[field]])
    );

    frappe.call({
        method: "india_compliance.gst_india.overrides.transaction.get_gst_details",
        args: {
            party_details: JSON.stringify(party_details),
            doctype: frm.doc.doctype,
            company: frm.doc.company,
        },
        callback(r) {
            if (!r.message) return;
            frm.set_value(r.message);
        },
    });
}

function validate_overseas_gst_category(doctype) {
    frappe.ui.form.on(doctype, {
        gst_category(frm) {
            const { enable_overseas_transactions } = gst_settings;
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
