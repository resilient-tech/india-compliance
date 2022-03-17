function update_export_type(doctype) {
    frappe.ui.form.on(doctype, {
        gst_category: function (frm) {
            if (["SEZ", "Overseas"].includes(frm.doc.gst_category)) {
                frappe.call({
                    method: "india_compliance.gst_india.overrides.invoice.get_export_type",
                    callback: function (r) {
                        if (!r.message) return;
                        frm.set_value("export_type", r.message);
                    },
                });
            } else {
                frm.set_value("export_type", "");
            }
        },
    });
}
