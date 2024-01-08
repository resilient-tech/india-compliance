frappe.ui.form.on("Document Naming Settings", {
    transaction_type: show_gst_invoice_no_banner,
});

function show_gst_invoice_no_banner(frm) {
    frm.dashboard.clear_headline();
    if (!show_gst_gst_invoice_no_banner(frm.doc.transaction_type)) return;

    frm.dashboard.set_headline_alert(
        `GST Invoice Number cannot exceed 14 characters and
            should start with an alphanumeric character.
            It can only contain alphanumeric characters, dash (-) and slash (/).`,
        "blue"
    );
}

function show_gst_gst_invoice_no_banner(transaction_type) {
    return (
        transaction_type === "Sales Invoice" ||
        (transaction_type === "Purchase Invoice" &&
            gst_settings.enable_e_waybill_from_pi) ||
        (transaction_type === "Delivery Note" && gst_settings.enable_e_waybill_from_dn)
    );
}
