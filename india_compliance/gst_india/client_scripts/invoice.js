function update_export_type(doctype) {
    frappe.ui.form.on(doctype, {
        async gst_category(frm) {
            if (!["SEZ", "Overseas"].includes(frm.doc.gst_category)) {
                return frm.set_value("is_export_with_gst", 0);
            }

            // TODO: categories should not be visible if not enabled
            const { gst_settings } = frappe.boot;
            if (!gst_settings.enable_overseas_transactions) {
                frappe.throw(
                    // prettier-ignore
                    __("Please enable SEZ / Overseas transactions in GST Settings first")
                );
            }

            frm.set_value(
                "is_export_with_gst",
                gst_settings.default_with_payment_of_tax ? 1 : 0
            );
        },
    });
}
