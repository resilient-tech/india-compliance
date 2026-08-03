// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("ISD Recipient Invoice", {
    onload(frm) {
        frm.isd_controller = new india_compliance.ISDController(frm);
        frm.set_query("itc_claim_period", () => ({
            query: "india_compliance.gst_india.utils.itc_claim.get_itc_period_options",
            params: {
                company_gstin: frm.doc.company_gstin,
                posting_date: frm.doc.posting_date,
            },
        }));
        if (frm.is_new() && !frm.doc.company) {
            frm.set_value("company", frappe.defaults.get_user_default("Company"));
        }
        india_compliance.set_itc_claim_period_status(frm);
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

    party_address(frm) {
        frm.isd_controller.set_address_display("party_address", "party_address_display");
        frm.isd_controller.set_pos("party_address", "party_pos");
    },

    company_address(frm) {
        frm.isd_controller.set_address_display("company_address", "company_address_display");
        frm.isd_controller.set_pos("company_address", "company_pos");
    },

    // the credit received is driven by distributed_*, so the ratio is informational here
    branch_turnover(frm) {
        frm.isd_controller.calculate_distribution_ratio();
    },

    total_turnover(frm) {
        frm.isd_controller.calculate_distribution_ratio();
    },
});

const recalculate = (frm) => frm.isd_controller.recalculate();

frappe.ui.form.on("ISD Source Item", {
    ...Object.fromEntries(
        [
            ...frappe.boot.gst_tax_types.map((tax_type) => `distributed_${tax_type}`),
            "distributed_expense",
            "is_ineligible_for_itc",
            "source_items_remove",
        ].map((field) => [field, recalculate]),
    ),

    source_items_add(frm) {
        frm.isd_controller.set_default_expense_head();
        recalculate(frm);
    },
});
