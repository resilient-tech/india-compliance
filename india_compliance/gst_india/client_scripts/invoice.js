function update_export_type(doctype) {
    frappe.ui.form.on(doctype, {
        async gst_category(frm) {
            if (!["SEZ", "Overseas"].includes(frm.doc.gst_category)) {
                return frm.set_value("export_type", "");
            }

            const { message } = await frappe.call(
                "india_compliance.gst_india.overrides.invoice.get_export_type"
            );

            if (!message) return;
            frm.set_value("export_type", message);
        },
    });
}
