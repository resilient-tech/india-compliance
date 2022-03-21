{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Address";

update_invalid_gstin(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    async refresh(frm) {
        if (!frm.is_new() || !frm.doc.links || frm.doc.gstin) return;

        const row = frm.doc.links[0];
        if (!["Customer", "Supplier", "Company"].includes(row.link_doctype)) return;

        const { message } = await frappe.db.get_value(
            row.link_doctype,
            row.link_name,
            ["gstin", "gst_category"]
        );

        if (!message) return;
        frm.set_value("gstin", message.gstin || "");
        frm.set_value("gst_category", message.gst_category || "");
    },
});
