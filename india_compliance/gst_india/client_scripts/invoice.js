function validate_overseas_gst_category(doctype) {
    frappe.ui.form.on(doctype, {
        async gst_category(frm) {
            const { gst_settings } = frappe.boot;
            if (
                !["SEZ", "Overseas"].includes(frm.doc.gst_category) ||
                gst_settings.enable_overseas_transactions
            )
                return;

            // TODO: categories should not be visible if not enabled
            frappe.throw(
                // prettier-ignore
                __("Please enable SEZ / Overseas transactions in GST Settings first")
            );
        },
    });
}
