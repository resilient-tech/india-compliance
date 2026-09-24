// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("ISD Distribution Invoice", {
    onload(frm) {
        frm.isd_controller = new india_compliance.ISDController(frm);
        if (frm.is_new() && !frm.doc.company) {
            frm.set_value("company", frappe.defaults.get_user_default("Company"));
        }
    },

    refresh(frm) {
        frm.isd_controller.set_labels();
        frm.isd_controller.toggle_expense_fields();
        frm.isd_controller.set_common_buttons();
        frm.isd_controller.set_grand_total();

        if (frm.doc.docstatus !== 1) return;

        if (frappe.model.can_create("ISD Recipient Invoice")) {
            frm.add_custom_button(
                __("ISD Recipient Invoice"),
                () => {
                    frappe.model.open_mapped_doc({
                        method: "india_compliance.gst_india.doctype.isd_distribution_invoice.isd_distribution_invoice.create_isd_recipient_invoice",
                        frm: frm,
                    });
                },
                __("Create"),
            );
        }

        if (!frm.doc.is_credit_note && frappe.model.can_create("ISD Distribution Invoice")) {
            frm.add_custom_button(
                __("Credit Note"),
                () => {
                    frappe.model.open_mapped_doc({
                        method: "india_compliance.gst_india.doctype.isd_distribution_invoice.isd_distribution_invoice.create_credit_note",
                        frm: frm,
                    });
                },
                __("Create"),
            );
        }
    },

    async company(frm) {
        await frm.isd_controller.load_company_defaults();
        await frm.isd_controller.fetch_autofill("company");
    },

    is_against_party(frm) {
        frm.isd_controller.set_labels();
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

    async company_address(frm) {
        frm.isd_controller.set_address_display("company_address", "company_address_display");
        await frm.isd_controller.set_place_of_supply("company_address", "company_pos");
        if (frm.__updating_isd_autofill) return;
        recalculate(frm);
    },

    async party_address(frm) {
        frm.doc.party_address_copy = frm.doc.party_address;
        frm.refresh_field("party_address_copy");

        if (!frm.__updating_isd_autofill) {
            await frm.isd_controller.fetch_autofill("party_address");
        }
        frm.isd_controller.set_address_display("party_address", "party_address_display");
        await frm.isd_controller.set_place_of_supply("party_address", "party_pos");
        await recalculate(frm);
    },

    purchase_invoice: fetch_source_items,

    is_ineligible_for_itc(frm) {
        frm.isd_controller.set_labels();
        return fetch_source_items(frm);
    },

    branch_turnover(frm) {
        frm.isd_controller.calculate_distribution_ratio();
        frm.isd_controller.recalculate();
    },

    total_turnover(frm) {
        frm.isd_controller.calculate_distribution_ratio();
        frm.isd_controller.recalculate();
    },

    is_credit_note(frm) {
        frm.isd_controller.clear_credit_note_against();
        frm.isd_controller.recalculate();
    },
});

async function fetch_source_items(frm) {
    const { purchase_invoice, is_ineligible_for_itc } = frm.doc;

    frm.clear_table("source_items");
    if (purchase_invoice) {
        const { message: items } = await frappe.call({
            method: "india_compliance.gst_india.utils.isd.get_source_items_from_purchase_invoice",
            args: { purchase_invoice, is_ineligible_for_itc },
        });
        if (frm.doc.purchase_invoice !== purchase_invoice) return;
        for (const item of items || []) frm.add_child("source_items", item);
    }
    frm.refresh_field("source_items");
    await recalculate(frm);
}

const recalculate = async (frm) => {
    if (frm.doctype !== "ISD Distribution Invoice") return;

    frm.clear_table("taxes");
    frm.isd_controller.set_available_taxes();
    await frm.isd_controller.recalculate();
};

frappe.ui.form.on("ISD Source Item", {
    source_items_remove: recalculate,
});
