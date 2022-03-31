export function update_export_type(doctype) {
    frappe.ui.form.on(doctype, {
        async gst_category(frm) {
            if (!["SEZ", "Overseas"].includes(frm.doc.gst_category)) {
                return frm.set_value("export_type", "");
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
                "export_type",
                gst_settings.default_without_payment_of_tax
                    ? "Without Payment of Tax"
                    : "With Payment of Tax"
            );
        },
    });
}
