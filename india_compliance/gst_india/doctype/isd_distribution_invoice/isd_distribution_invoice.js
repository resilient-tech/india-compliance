// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("ISD Distribution Invoice", {
    onload(frm) {
        frm.isd_controller = new india_compliance.ISDController(frm);
        if (frm.is_new() && !frm.doc.company) {
            frm.set_value("company", frappe.defaults.get_user_default("Company"));
        }

        frm.set_query("credit_note_against", () => ({
            filters: { docstatus: 1, is_credit_note: 0 },
        }));
    },

    on_submit(frm) {
        if (frm.doc.is_against_party) return;

        const create_recipient = (submit_on_creation) => {
            frappe.call({
                method: "india_compliance.gst_india.doctype.isd_distribution_invoice.isd_distribution_invoice.create_isd_recipient_invoice",
                args: { source_name: frm.doc.name, submit_on_creation },
                freeze: true,
                freeze_message: __("Creating ISD Recipient Invoice..."),
            });
        };

        frappe.confirm(
            __("Do you wish to auto-submit the ISD Recipient Invoice?"),
            () => create_recipient(1),
            () => create_recipient(0),
        );
    },

    refresh(frm) {
        // source_items are populated from the linked purchase invoice, never edited by hand
        frm.set_df_property("source_items", "read_only", 1);
        frm.isd_controller.set_provisional_labels();
        frm.isd_controller.toggle_expense_fields();
        frm.isd_controller.set_common_buttons();

        if (frm.doc.docstatus !== 1) return;

        if (frm.doc.is_against_party && frappe.model.can_create("ISD Recipient Invoice")) {
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

        if (frappe.model.can_read("ISD Recipient Invoice")) {
            frm.add_custom_button(
                __("Recipient Invoice"),
                async () => {
                    // one active (non-cancelled) recipient invoice per distribution invoice
                    const { message } = await frappe.db.get_value(
                        "ISD Recipient Invoice",
                        { isd_distribution_invoice_reference: frm.doc.name, docstatus: ["<", 2] },
                        "name",
                    );

                    if (!message?.name) {
                        frappe.msgprint(__("No ISD Recipient Invoice found for {0}.", [frm.doc.name]));
                        return;
                    }

                    frappe.set_route("Form", "ISD Recipient Invoice", message.name);
                },
                __("View"),
            );
        }
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

    async distribution_address(frm) {
        frm.isd_controller.set_address_display("distribution_address", "distribution_address_display");
        await frm.isd_controller.set_pos("distribution_address", "distribution_pos");
        await frm.isd_controller.recalculate();
    },

    async recipient_address(frm) {
        frm.isd_controller.set_address_display("recipient_address", "recipient_address_display");
        await frm.isd_controller.set_pos("recipient_address", "recipient_pos");
        if (!frm.__updating_isd_autofill) {
            await frm.isd_controller.fetch_autofill("recipient_address");
        }
        await frm.isd_controller.recalculate();
    },

    async purchase_invoice(frm) {
        frm.clear_table("source_items");
        if (frm.doc.purchase_invoice) {
            const { message: items } = await frappe.call({
                method: "india_compliance.gst_india.utils.isd.get_source_items_from_purchase_invoice",
                args: { purchase_invoice: frm.doc.purchase_invoice },
            });
            for (const item of items || []) frm.add_child("source_items", item);
        }
        frm.refresh_field("source_items");
        await frm.isd_controller.recalculate();
    },

    branch_turnover(frm) {
        calculate_distribution_ratio(frm);
        frm.isd_controller.recalculate();
    },

    total_turnover(frm) {
        calculate_distribution_ratio(frm);
        frm.isd_controller.recalculate();
    },

    is_credit_note(frm) {
        frm.isd_controller.recalculate();
    },
});

frappe.ui.form.on("ISD Source Item", {
    async source_items_remove(frm) {
        await frm.isd_controller.recalculate();
    },

    is_ineligible_for_itc(frm) {
        frm.isd_controller.calculate_taxes_and_totals();
    },
});

function calculate_distribution_ratio(frm) {
    const { branch_turnover, total_turnover } = frm.doc;

    const distribution_ratio = total_turnover ? (flt(branch_turnover) / flt(total_turnover)) * 100 : 0;
    if (distribution_ratio > 100) {
        frappe.throw(__("Distribution Ratio cannot be greater than 100%"));
    }

    frm.set_value("distribution_ratio", distribution_ratio);
}
