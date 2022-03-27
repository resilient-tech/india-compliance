{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Address";

validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    country(frm) {
        set_state_options(frm);
    },
    async refresh(frm) {
        set_state_options(frm);

        // set default values for GST fields
        if (!frm.is_new() || !frm.doc.links || frm.doc.gstin) return;

        const row = frm.doc.links[0];
        if (!["Customer", "Supplier", "Company"].includes(row.link_doctype)) return;

        // Try to get clean doc from locals
        const doc = frappe.get_doc(row.link_doctype, row.link_name);

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

function set_state_options(frm) {
    const state_field = frm.get_field("state");
    if (frm.doc.country !== "India") {
        state_field.set_data([]);
        return;
    }

    state_field.set_data(state_field.df.options_for_india || []);
}
