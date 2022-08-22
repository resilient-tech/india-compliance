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
    fetch_tax_template(doctype);
    validate_overseas_gst_category(doctype);
    set_reverse_charge_for_unregistered_purchase(doctype);
}

function fetch_gst_details(doctype) {
    const event_fields = [];

    // we are using address below to prevent multiple event triggers
    if (in_list(frappe.boot.sales_doctypes, doctype)) {
        event_fields.push("customer_address", "company_address");
    } else {
        event_fields.push("supplier_address", "billing_address");
    }

    const events = Object.fromEntries(
        event_fields.map(field => [field, update_gst_details])
    );

    frappe.ui.form.on(doctype, events);
}

async function update_gst_details(frm) {
    if (frm.__gst_update_triggered || frm.updating_party_details || !frm.doc.company)
        return;

    const party_type = ic.get_party_type(frm.doc.doctype).toLowerCase();
    if (!frm.doc[party_type]) return;

    frm.__gst_update_triggered = true;
    // wait for GSTINs to get fetched
    await frappe.after_ajax().then(() => (frm.__gst_update_triggered = false));

    const is_sales_transaction = in_list(frappe.boot.sales_doctypes, frm.doc.doctype);
    const party_fields = ["gst_category", "company_gstin", party_type];
    if (is_sales_transaction)
        party_fields.push("customer_address", "billing_address_gstin");
    else party_fields.push("supplier_address", "supplier_gstin");

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
            const response = r.message;

            // if is_reverse_charge, don't set taxes
            if (is_sales_transaction && frm.doc.is_reverse_charge) {
                delete response.taxes;
                delete response.taxes_and_charges;
            }

            frm.set_value(response);
        },
    });
}

function fetch_tax_template(doctype) {
    const event_fields = [
        "company_gstin",
        "gst_category",
        "is_reverse_charge",
        "place_of_supply",
    ];

    // we are using address below to prevent multiple event triggers
    if (in_list(frappe.boot.sales_doctypes, doctype))
        event_fields.push("is_export_with_gst");

    const events = Object.fromEntries(
        event_fields.map(field => [field, update_tax_template])
    );

    frappe.ui.form.on(doctype, events);
}

async function update_tax_template(frm) {
    if (
        frm.__updating_tax_template ||
        frm.__gst_update_triggered ||
        frm.updating_party_details ||
        !frm.doc.place_of_supply
    )
        return;

    frm.__updating_tax_template = true;
    const party_type = ic.get_party_type(frm.doc.doctype).toLowerCase();
    if (!frm.doc[party_type]) return;

    // wait for Tax Templates to get fetched
    const doc_fields = [
        "doctype",
        "company",
        "gst_category",
        "company_gstin",
        party_type,
        "is_reverse_charge",
        "place_of_supply",
    ];
    if (in_list(frappe.boot.sales_doctypes, frm.doc.doctype)) {
        doc_fields.push("billing_address_gstin", "is_export_with_gst");
    } else {
        doc_fields.push("supplier_gstin", "supplier_address");
    }

    const doc_details = Object.fromEntries(
        doc_fields.map(field => [field, frm.doc[field]])
    );

    frappe.call({
        method: "india_compliance.gst_india.overrides.transaction.get_tax_template",
        args: { doc: doc_details },
        callback(r) {
            if (!r.message) return;
            frm.set_value(r.message);
            frm.__updating_tax_template = false;
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

function set_reverse_charge_for_unregistered_purchase(doctype) {
    if (
        in_list(frappe.boot.sales_doctypes, doctype) ||
        !gst_settings.reverse_charge_for_unregistered_purchase
    )
        return;

    frappe.ui.form.on(doctype, {
        setup: patch_calculate_taxes_and_totals,
    });
}

function patch_calculate_taxes_and_totals(frm) {
    const calculate_taxes_and_totals = frm.cscript.calculate_taxes_and_totals;

    frm.cscript.calculate_taxes_and_totals = function (...args) {
        calculate_taxes_and_totals.apply(this, args);

        if (frm.doc.base_grand_total >= gst_settings.reverse_charge_threshold)
            toggle_reverse_charge(frm, true);
        else toggle_reverse_charge(frm, false);
    };
}

function toggle_reverse_charge(frm, enable) {
    if (
        (enable && frm.doc.is_reverse_charge) ||
        (!enable && !frm.doc.is_reverse_charge)
    )
        return;

    frm.set_value("is_reverse_charge", enable);
}
