{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Address";

update_invalid_gstin(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    refresh: function (frm) {
        if (!frm.doc.__islocal || !frm.doc.links || frm.doc.gstin) return;
        const row = frm.doc.links[0];
        if (!["Customer", "Supplier", "Company"].includes(row.link_doctype)) return;
        frappe.db
            .get_value(row.link_doctype, row.link_name, [
                "gstin",
                "gst_category",
            ])
            .then((r) => {
                if(!r.message) return;
                frm.set_value("gstin", r.message.gstin || "");
                frm.set_value("gst_category", r.message.gst_category || "");
            });
    },
});

