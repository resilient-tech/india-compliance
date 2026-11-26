// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier", {
    refresh: set_msme_registration_description,
    msme_registration: set_msme_registration_description,
    gstin: offer_msme_registration_for_pan,
    pan: offer_msme_registration_for_pan,
});

async function offer_msme_registration_for_pan(frm) {
    const { pan } = frm.doc;
    if (!frm.is_new() || frm.doc.msme_registration || !pan) return;

    const msme_registration = await frappe.xcall(
        "india_compliance.income_tax_india.utils.msme.get_msme_registration_for_pan",
        { pan },
    );
    if (!msme_registration || frm.doc.msme_registration || frm.doc.pan !== pan) return;

    frappe.confirm(
        __("Another Supplier with PAN {0} uses MSME Registration {1}. Link it here?", [
            pan,
            msme_registration,
        ]),
        () => frm.set_value("msme_registration", msme_registration),
    );
}

async function set_msme_registration_description(frm) {
    const field = frm.get_field("msme_registration");
    if (!frm.doc.msme_registration) return field.set_description("");

    const { message } = await frappe.call({
        method: "india_compliance.income_tax_india.utils.msme.get_msme_registration_status",
        args: { msme_registration: frm.doc.msme_registration },
    });

    if (!message) return field.set_description("");

    const classification = message.enterprise_type
        ? `${__(message.enterprise_type)} - ${__(message.activity)}`
        : __("Not Classified");

    field.set_description(
        message.valid
            ? classification
            : `<span class="indicator red">${classification}, ${__("Invalid")}</span>`,
    );
}

india_compliance.set_msme_payment_terms = ({ supplier, payment_terms }) => {
    frappe.hide_msgprint();
    if (cur_frm?.doctype !== "Supplier" || cur_frm.doc.name !== supplier) return;

    cur_frm.set_value("payment_terms", payment_terms).then(() => cur_frm.save());
};
