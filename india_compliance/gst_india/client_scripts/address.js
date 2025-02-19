{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Address";

validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
show_overseas_disabled_warning(DOCTYPE);
set_gstin_options_and_status(DOCTYPE);
set_gst_category(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    country(frm) {
        india_compliance.set_state_options(frm);

        if (!frm.doc.country) return;

        // Assume default country to be India for now
        // Automatically set GST Category as Overseas if country is not India
        if (frm.doc.country != "India") frm.set_value("gst_category", "Overseas");
        else frm.trigger("gstin");
    },
    async refresh(frm) {
        india_compliance.set_state_options(frm);

        frm.add_custom_button(__("Update Address"), () => update_address_fields(frm));

        // set default values for GST fields
        if (!frm.is_new() || !frm.doc.links || !frm.doc.links.length || frm.doc.gstin)
            return;

        const row = frm.doc.links[0];
        if (!frappe.boot.gst_party_types.includes(row.link_doctype)) return;

        // Try to get clean doc from locals
        let doc = frappe.get_doc(row.link_doctype, row.link_name);

        // Fallback to DB
        if (!doc || doc.__unsaved || doc.__islocal) {
            const { message } = await frappe.db.get_value(
                row.link_doctype,
                row.link_name,
                ["gstin", "gst_category"]
            );

            if (message) {
                doc = message;
            } else {
                return;
            }
        }

        frm.set_value("gstin", doc.gstin || "");
        frm.set_value("gst_category", doc.gst_category || "");
    },
});

function update_address_fields(frm) {
    const original_quick_entry_form = frappe.ui.form.AddressQuickEntryForm;

    frappe.ui.form.AddressQuickEntryForm = class extends (
        frappe.ui.form.AddressQuickEntryForm
    ) {
        title = "Update Address";

        get_dynamic_link_fields() {
            return [];
        }

        update_doc() {
            const doc = super.update_doc();
            frm.reload_doc();
            return doc;
        }
    };

    frappe.db.get_doc(DOCTYPE, frm.doc.name).then(doc => {
        frappe.ui.form.make_quick_entry(
            DOCTYPE,
            null,
            dialog => dialog.set_value("_gstin", frm.doc.gstin),
            doc
        );
        frappe.ui.form.AddressQuickEntryForm = original_quick_entry_form;
    });
}
