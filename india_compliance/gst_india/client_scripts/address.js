{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Address";

update_old_gstin(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    refresh: function (frm) {
        if (!frm.doc.__islocal || !frm.doc.links || frm.doc.gstin) return;
        const row = frm.doc.links[0];
        frappe.db
            .get_value(row.link_doctype, row.link_name, [
                "gstin",
                "gst_category",
            ])
            .then((r) => {
                frm.set_value("gstin", r.message.gstin);
                frm.set_value("gst_category", r.message.gst_category);
            });
    },
});

