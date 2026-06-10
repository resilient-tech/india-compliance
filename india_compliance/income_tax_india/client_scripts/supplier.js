// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier", {
    refresh(frm) {
        india_compliance.setup_indian_fiscal_year_options(frm, "india_msme_classification");
    },

    udyam_number(frm) {
        let udyam_number = frm.doc.udyam_number;
        // validate only once the full 19-character number is entered
        if (!udyam_number || udyam_number.length < 19) return;

        udyam_number = india_compliance.validate_udyam_number(udyam_number);

        frm.doc.udyam_number = udyam_number;
        frm.refresh_field("udyam_number");
    },
});
