// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier", {
    refresh: set_msme_registration_description,
    msme_registration: set_msme_registration_description,
});

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
