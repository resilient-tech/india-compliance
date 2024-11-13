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

const SUBCONTRACTING_DOCTYPES = [
    "Stock Entry",
    "Subcontracting Order",
    "Subcontracting Receipt",
];

for (const doctype of TRANSACTION_DOCTYPES) {
    fetch_gst_details(doctype);
    validate_overseas_gst_category(doctype);
    set_and_validate_gstin_status(doctype);
}

for (const doctype of SUBCONTRACTING_DOCTYPES) {
    fetch_party_details(doctype);
    fetch_gst_details(doctype);
}

for (const doctype of ["Sales Invoice", "Delivery Note"]) {
    ignore_port_code_validation(doctype);
}

for (const doctype of ["Sales Invoice", "Sales Order", "Delivery Note"]) {
    set_e_commerce_ecommerce_supply_type(doctype);
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
        event_fields.push(
            "customer_address",
            "shipping_address_name",
            "is_export_with_gst"
        );
    } else if (doctype === "Stock Entry") {
        event_fields.push("bill_from_address", "bill_to_address");
    } else if (["Subcontracting Order", "Subcontracting Receipt"].includes(doctype)) {
        event_fields.push("supplier_gstin");
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
        (["place_of_supply", "bill_to_address"].includes(event) &&
            frm.__updating_gst_details)
    )
        return;

    const party_type = india_compliance.get_party_type(frm.doc.doctype).toLowerCase();
    const party_fieldname = frm.doc.doctype === "Quotation" ? "party_name" : party_type;
    const party = frm.doc[party_fieldname];

    const same_gstin_stock_entry =
        frm.doc.doctype === "Stock Entry" &&
        ["Material Transfer", "Material Issue"].includes(frm.doc.purpose) &&
        !frm.doc.is_return;

    if (!(party || same_gstin_stock_entry)) return;

    if (
        [
            "company_gstin",
            "bill_from_gstin",
            "bill_to_address",
            "customer_address",
            "shipping_address_name",
            "supplier_address",
        ].includes(event)
    ) {
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
            "shipping_address_name",
            "billing_address_gstin",
            "is_export_with_gst"
        );
    } else if (frm.doc.doctype === "Stock Entry") {
        fieldnames_to_set.push(
            "bill_from_gstin",
            "bill_to_gstin",
            "bill_from_address",
            "bill_to_address"
        );

        party_details["is_outward_stock_entry"] = same_gstin_stock_entry;
        party_details["is_inward_stock_entry"] =
            frm.doc.purpose === "Material Transfer" && frm.doc.is_return;
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
        method:
            method ||
            "india_compliance.gst_india.overrides.transaction.get_gst_details",
        args,
        async callback(r) {
            if (!r.message) return;

            frm.__updating_gst_details = true;
            await frm.set_value(r.message);
            frm.__updating_gst_details = false;
        },
    });
};

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
            if (frm.doc[gstin_field_name]) _set_gstin_status(frm, gstin_field_name);
        },

        [gstin_field_name](frm) {
            _set_and_validate_gstin_status(frm, gstin_field_name);
        },

        gst_transporter_id(frm) {
            india_compliance.validate_gst_transporter_id(frm.doc.gst_transporter_id);
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
        gstin_doc = await india_compliance.set_gstin_status(
            gstin_field,
            date_field.value
        );

        frm._gstin_doc = frm._gstin_doc || {};
        frm._gstin_doc[gstin] = gstin_doc;
    } else {
        gstin_field.set_description(
            india_compliance.get_gstin_status_desc(
                gstin_doc?.status,
                gstin_doc?.last_updated_on
            )
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

function set_e_commerce_ecommerce_supply_type(doctype) {
    const event_fields = ["ecommerce_gstin", "is_reverse_charge"];

    const events = Object.fromEntries(
        event_fields.map(field => [
            field,
            frm => _set_e_commerce_ecommerce_supply_type(frm),
        ])
    );

    frappe.ui.form.on(doctype, events);
}

function _set_e_commerce_ecommerce_supply_type(frm) {
    if (!gst_settings.enable_sales_through_ecommerce_operators) return;

    if (!frm.doc.ecommerce_gstin) {
        frm.set_value("ecommerce_supply_type", "");
        return;
    }

    if (frm.doc.is_reverse_charge) {
        frm.set_value("ecommerce_supply_type", "Liable to pay tax u/s 9(5)");
    } else {
        frm.set_value("ecommerce_supply_type", "Liable to collect tax u/s 52(TCS)");
    }
}

function fetch_party_details(doctype) {
    let company_gstin_field = "company_gstin";
    let is_inward_stock_entry = false;

    if (doctype === "Stock Entry") {
        company_gstin_field = "bill_from_gstin";
    }

    frappe.ui.form.on(doctype, {
        supplier(frm) {
            if (
                frm.doc.doctype === "Stock Entry" &&
                frm.doc.purpose === "Material Transfer" &&
                frm.doc.is_return
            ) {
                company_gstin_field = "bill_to_gstin";
                is_inward_stock_entry = true;
            }

            setTimeout(() => {
                const party_details = {
                    [company_gstin_field]: frm.doc[company_gstin_field],
                    supplier: frm.doc.supplier,
                    is_inward_stock_entry,
                };
                const args = {
                    party_details: JSON.stringify(party_details),
                    posting_date: frm.doc.posting_date || frm.doc.transaction_date,
                };

                toggle_link_validation(frm, ["supplier_address"], false);
                erpnext.utils.get_party_details(
                    frm,
                    "india_compliance.gst_india.overrides.transaction.get_party_details_for_subcontracting",
                    args,
                    () => {
                        toggle_link_validation(frm, ["supplier_address"], true);
                    }
                );
            }, 0);
        },
    });
}

function toggle_link_validation(frm, fields, validate = true) {
    fields.forEach(field => {
        const df = frm.get_field(field).df;
        if (df) df.ignore_link_validation = !validate;
    });
}
