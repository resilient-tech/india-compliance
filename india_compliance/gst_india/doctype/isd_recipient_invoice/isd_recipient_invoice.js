// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("ISD Recipient Invoice", {
    onload(frm) {
        frm.isd_controller = new india_compliance.ISDController(frm);
        if (frm.is_new() && !frm.doc.company) {
            frm.set_value("company", frappe.defaults.get_user_default("Company"));
        }
    },

    refresh(frm) {
        frm.isd_controller.set_provisional_labels();
        frm.isd_controller.toggle_expense_fields();
        frm.isd_controller.set_common_buttons();
    },

    async company(frm) {
        await frm.isd_controller.load_company_defaults();
        await frm.isd_controller.fetch_autofill("company");
    },

    is_against_party(frm) {
        frm.isd_controller.set_provisional_labels();
        if (frm.__updating_isd_autofill) return;
        frm.isd_controller.fetch_autofill("is_against_party");
    },

    party_type(frm) {
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party) return;
        frm.isd_controller.fetch_autofill("party_type");
    },

    party(frm) {
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party || !frm.doc.party) return;
        frm.isd_controller.fetch_autofill("party");
    },

    distribution_address(frm) {
        frm.isd_controller.set_address_display("distribution_address", "distribution_address_display");
        frm.isd_controller.set_pos("distribution_address", "distribution_pos");
    },

    recipient_address(frm) {
        frm.isd_controller.set_address_display("recipient_address", "recipient_address_display");
        frm.isd_controller.set_pos("recipient_address", "recipient_pos");
    },
});
