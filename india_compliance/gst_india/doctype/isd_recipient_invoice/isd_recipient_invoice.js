// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("ISD Recipient Invoice", {
    setup(frm) {
        india_compliance.setup_itc_claim_period_query(frm);
    },

    onload(frm) {
        frm.isd_controller = new india_compliance.ISDController(frm);
        if (frm.is_new() && !frm.doc.company) {
            frm.set_value("company", frappe.defaults.get_user_default("Company"));
        }
    },

    refresh(frm) {
        india_compliance.set_itc_claim_period_status(frm);

        india_compliance.set_reconciliation_status(
            frm,
            frm.doc.isd_distribution_invoice_reference
                ? "isd_distribution_invoice_reference"
                : "external_isd_invoice_number",
        );

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

    party_address(frm) {
        frm.isd_controller.set_address_display("party_address", "party_address_display");
        frm.isd_controller.set_place_of_supply("party_address", "party_pos");
    },

    company_address(frm) {
        frm.isd_controller.set_address_display("company_address", "company_address_display");
        frm.isd_controller.set_place_of_supply("company_address", "company_pos");
    },

    is_credit_note(frm) {
        frm.isd_controller.clear_credit_note_against();
    },

    // the credit received is driven by distributed_*, so the ratio is informational here
    branch_turnover(frm) {
        frm.isd_controller.calculate_distribution_ratio();
    },

    total_turnover(frm) {
        frm.isd_controller.calculate_distribution_ratio();
    },
});

const recalculate = (frm) => {
    if (frm.doctype !== "ISD Recipient Invoice") return;
    frm.isd_controller.recalculate();
};

// the credit received is typed in row by row, so every amount field drives the totals
const RECALCULATE_ON = [
    ...(frappe.boot.gst_tax_types || []).map((tax_type) => `distributed_${tax_type}`),
    "distributed_expense",
    "is_ineligible_for_itc",
];

frappe.ui.form.on("ISD Source Item", {
    ...Object.fromEntries(RECALCULATE_ON.map((field) => [field, recalculate])),

    source_items_remove: recalculate,

    source_items_add(frm) {
        if (frm.doctype !== "ISD Recipient Invoice") return;
        frm.isd_controller.set_default_expense_head();
        recalculate(frm);
    },
});
