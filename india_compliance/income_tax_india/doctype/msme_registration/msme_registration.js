// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

const UDYAM_NUMBER_LENGTH = 19;

frappe.ui.form.on("MSME Registration", {
    refresh(frm) {
        india_compliance.setup_indian_fiscal_year_options(
            frm,
            "classifications",
            "financial_year",
            frm.doc.registration_date || undefined,
        );

        // both actions save the document, so unsaved changes would be swept along
        if (frm.is_new() || frm.is_dirty()) return;

        if (frm.doc.is_cancelled) {
            frm.add_custom_button(__("Undo Cancellation"), () =>
                frm
                    .call({
                        method: "undo_cancellation",
                        doc: frm.doc,
                        freeze: true,
                        freeze_message: __("Undoing Cancellation"),
                    })
                    .then(() => frm.refresh()),
            );
            return;
        }

        frm.add_custom_button(__("Mark as Cancelled"), () => show_cancellation_dialog(frm));
    },

    registration_date(frm) {
        // the years worth offering start where the registration does
        india_compliance.setup_indian_fiscal_year_options(
            frm,
            "classifications",
            "financial_year",
            frm.doc.registration_date || undefined,
        );

        // a lone classification is the one the registration was created with, so
        // it follows the date rather than being left describing another year
        if (frm.doc.classifications?.length !== 1) return;

        const [classification] = frm.doc.classifications;
        frappe.model.set_value(
            classification.doctype,
            classification.name,
            "financial_year",
            india_compliance.get_indian_fiscal_year(frm.doc.registration_date || undefined),
        );
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
            frm.call({
                method: "mark_as_cancelled",
                doc: frm.doc,
                args: values,
                freeze: true,
                freeze_message: __("Cancelling MSME Registration"),
            }).then(() => {
                dialog.hide();
                frm.refresh();
            });
        },
    });

    dialog.show();
}
