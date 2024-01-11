// functions in this file will apply to most transactions
// POS Invoice is a notable exception since it doesn't get created from the UI
frappe.provide("india_compliance");

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
    set_and_validate_gstin_status(doctype);
}

for (const doctype of ["Sales Invoice", "Delivery Note"]) {
    ignore_port_code_validation(doctype);
}

function fetch_gst_details(doctype) {
    const event_fields = [
        "tax_category",
        "company_gstin",
        "place_of_supply",
        "is_reverse_charge",
    ];

    // we are using address below to prevent multiple event triggers
    if (in_list(frappe.boot.sales_doctypes, doctype)) {
        event_fields.push("customer_address", "is_export_with_gst");
    } else {
        event_fields.push("supplier_address");
    }

    const events = Object.fromEntries(
        event_fields.map(field => [field, frm => update_gst_details(frm, field)])
    );

    frappe.ui.form.on(doctype, events);
}

async function update_gst_details(frm, event) {
    if (
        frm.updating_party_details ||
        !frm.doc.company ||
        (event === "place_of_supply" && frm.__updating_gst_details)
    )
        return;

    const party_type = india_compliance.get_party_type(frm.doc.doctype).toLowerCase();
    const party_fieldname = frm.doc.doctype === "Quotation" ? "party_name" : party_type;
    const party = frm.doc[party_fieldname];
    if (!party) return;

    if (in_list(["company_gstin", "customer_address", "supplier_address"], event)) {
        frm.__update_place_of_supply = true;
    }

    if (frm.__gst_update_triggered) return;
    frm.__gst_update_triggered = true;

    const args = {
        doctype: frm.doc.doctype,
        company: frm.doc.company,
    };

    // wait for GSTINs to get fetched
    await frappe.after_ajax();

    // reset flags
    frm.__gst_update_triggered = false;

    if (frm.__update_place_of_supply) {
        args.update_place_of_supply = 1;
        frm.__update_place_of_supply = false;
    }

    const party_details = {};

    // set "customer" or "supplier" (not applicable for Quotations with Lead)
    if (frm.doc.doctype !== "Quotation" || frm.doc.party_type === "Customer") {
        party_details[party_type] = party;
    }

    const fieldnames_to_set = [
        "tax_category",
        "gst_category",
        "company_gstin",
        "place_of_supply",
        "is_reverse_charge",
    ];

    if (in_list(frappe.boot.sales_doctypes, frm.doc.doctype)) {
        fieldnames_to_set.push(
            "customer_address",
            "billing_address_gstin",
            "is_export_with_gst"
        );
    } else {
        fieldnames_to_set.push("supplier_address", "supplier_gstin");
    }

    for (const fieldname of fieldnames_to_set) {
        party_details[fieldname] = frm.doc[fieldname];
    }

    args.party_details = JSON.stringify(party_details);

    india_compliance.fetch_and_update_gst_details(frm, args);
}

india_compliance.fetch_and_update_gst_details = function (frm, args, method) {
    frappe.call({
        method: method || "india_compliance.gst_india.overrides.transaction.get_gst_details",
        args,
        async callback(r) {
            if (!r.message) return;

            frm.__updating_gst_details = true;
            await frm.set_value(r.message);
            frm.__updating_gst_details = false;
        },
    });
}

function validate_overseas_gst_category(doctype) {
    frappe.ui.form.on(doctype, {
        gst_category(frm) {
            const { enable_overseas_transactions } = gst_settings;
            if (!is_overseas_transaction(frm) || enable_overseas_transactions) return;

            frappe.throw(
                __("Please enable SEZ / Overseas transactions in GST Settings first")
            );
        },
    });
}

function is_overseas_transaction(frm) {
    if (frm.doc.gst_category === "SEZ") return true;

    if (frappe.boot.sales_doctypes) return is_foreign_transaction(frm);

    return frm.doc.gst_category === "Overseas";
}

function ignore_port_code_validation(doctype) {
    frappe.ui.form.on(doctype, {
        onload(frm) {
            frm.set_df_property("port_code", "ignore_validation", 1);
        },
    });
}

function is_foreign_transaction(frm) {
    return (
        frm.doc.gst_category === "Overseas" &&
        frm.doc.place_of_supply === "96-Other Countries"
    );
}

function set_and_validate_gstin_status(doctype) {
    const gstin_field_name = frappe.boot.sales_doctypes.includes(doctype)
        ? "billing_address_gstin"
        : "supplier_gstin";

    frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (frm.doc[gstin_field_name])
                _set_gstin_status(frm, gstin_field_name);
        },

        [gstin_field_name](frm) {
            _set_and_validate_gstin_status(frm, gstin_field_name);
        },

        posting_date(frm) {
            if (frm.get_field("posting_date"))
                _set_and_validate_gstin_status(frm, gstin_field_name);
        },

        transaction_date(frm) {
            if (frm.get_field("transaction_date"))
                _set_and_validate_gstin_status(frm, gstin_field_name);
        },
    });
}

async function _set_and_validate_gstin_status(frm, gstin_field_name) {
    const gstin_doc = await _set_gstin_status(frm, gstin_field_name);
    if (!gstin_doc) return;

    validate_gstin_status(gstin_doc, frm, gstin_field_name);
}

async function _set_gstin_status(frm, gstin_field_name) {
    const gstin_field = frm.get_field(gstin_field_name);
    const gstin = gstin_field.value;
    const date_field =
        frm.get_field("posting_date") || frm.get_field("transaction_date");


    let gstin_doc = frm._gstin_doc?.[gstin];
    if (!gstin_doc) {
        gstin_doc = await india_compliance.set_gstin_status(gstin_field, date_field.value);

        frm._gstin_doc = frm._gstin_doc || {};
        frm._gstin_doc[gstin] = gstin_doc;
    } else {
        gstin_field.set_description(
            india_compliance.get_gstin_status_desc(gstin_doc?.status, gstin_doc?.last_updated_on)
        );
    }

    return gstin_doc;
}

function validate_gstin_status(gstin_doc, frm, gstin_field_name) {
    if (!gst_settings.validate_gstin_status) return;

    const date_field =
        frm.get_field("posting_date") || frm.get_field("transaction_date");

    const gstin_field = frm.get_field(gstin_field_name);
    const transaction_date = frappe.datetime.str_to_obj(date_field.value);
    const registration_date = frappe.datetime.str_to_obj(gstin_doc.registration_date);
    const cancelled_date = frappe.datetime.str_to_obj(gstin_doc.cancelled_date);

    if (!registration_date || transaction_date < registration_date)
        frappe.throw({
            message: __(
                "{0} is Registered on {1}. Please make sure that the {2} is on or after {1}",
                [
                    gstin_field.df.label,
                    frappe.datetime.str_to_user(gstin_doc.registration_date),
                    date_field.df.label,
                ]
            ),
            title: __("Invalid Party GSTIN"),
        });

    if (gstin_doc.status === "Cancelled" && transaction_date >= cancelled_date)
        frappe.throw({
            message: __(
                "{0} is Cancelled from {1}. Please make sure that the {2} is before {1}",
                [
                    gstin_field.df.label,
                    frappe.datetime.str_to_user(gstin_doc.cancelled_date),
                    date_field.df.label,
                ]
            ),
            title: __("Invalid Party GSTIN"),
        });

    if (!["Active", "Cancelled"].includes(gstin_doc.status))
        frappe.throw({
            message: __("Status of {0} is {1}", [
                gstin_field.df.label,
                gstin_doc.status,
            ]),
            title: __("Invalid GSTIN Status"),
        });
}

function show_gst_invoice_no_banner(frm) {
    frm.dashboard.clear_headline();
    if (
        !is_invoice_no_validation_required(
            frm.doc.transaction_type || frm.doc.document_type
        )
    )
        return;

    frm.dashboard.set_headline_alert(
        `Naming Series should <strong>not</strong> exceed 16 characters for GST. <a href="https://docs.indiacompliance.app/docs/miscellaneous/transaction_validations#document-name" target="_blank">Know more</a>`,
        "blue"
    );
}

function is_invoice_no_validation_required(transaction_type) {
    return (
        transaction_type === "Sales Invoice" ||
        (transaction_type === "Purchase Invoice" &&
            gst_settings.enable_e_waybill_from_pi) ||
        (transaction_type === "Delivery Note" &&
            gst_settings.enable_e_waybill_from_dn) ||
        (transaction_type === "Purchase Receipt" &&
            gst_settings.enable_e_waybill_from_pr)
    );
}
