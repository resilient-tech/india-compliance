// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier", {
    refresh: set_msme_registration_description,
    msme_registration: set_msme_registration_description,
});

async function set_msme_registration_description(frm) {
    const field = frm.get_field("msme_registration");
    if (!frm.doc.msme_registration || !frappe.model.can_read("MSME Registration")) {
        return field.set_description("");
    }

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

    const frm = frappe.views.formview.Supplier?.frm;
    if (frm?.doc.name !== supplier) return;

    frm.set_value("payment_terms", payment_terms).then(() => frm.save());
};

india_compliance.set_supplier_msme_registration = ({ supplier, msme_registration }) => {
    frappe.hide_msgprint();

    const frm = frappe.views.formview.Supplier?.frm;
    if (frm?.doc.name !== supplier) return;

    frm.set_value("msme_registration", msme_registration).then(() => frm.save());
};
