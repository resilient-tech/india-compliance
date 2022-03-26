{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Address";

update_gstin_in_other_documents(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    async refresh(frm) {
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
