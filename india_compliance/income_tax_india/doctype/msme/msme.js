// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

const UDYAM_NUMBER_LENGTH = 19;

frappe.ui.form.on("MSME", {
    refresh(frm) {
        india_compliance.setup_indian_fiscal_year_options(frm, "classifications");

        if (frm.is_new() || frm.doc.is_cancelled) return;

        frm.add_custom_button(__("Mark as Cancelled"), () => show_cancellation_dialog(frm));
    },

    udyam_number(frm) {
        let { udyam_number } = frm.doc;

        // validate only once the full number is entered
        if (!udyam_number || udyam_number.length < UDYAM_NUMBER_LENGTH) return;

        frm.doc.udyam_number = india_compliance.validate_udyam_number(udyam_number);
        frm.refresh_field("udyam_number");
    },
});

function show_cancellation_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Mark as Cancelled"),
        fields: [
            {
                fieldname: "cancelled_date",
                label: __("Cancelled Date"),
                fieldtype: "Date",
                reqd: 1,
                default: frappe.datetime.get_today(),
                description: __("Supplies accepted after this date are not covered by MSME."),
            },
            {
                fieldname: "unlink_suppliers",
                label: __("Remove from linked Suppliers"),
                fieldtype: "Check",
                default: 0,
            },
        ],
        primary_action_label: __("Mark as Cancelled"),
        primary_action(values) {
            frm.call("mark_as_cancelled", values).then(() => {
                dialog.hide();
                frm.reload_doc();
            });
        },
    });

    dialog.show();
}
