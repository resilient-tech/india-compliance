frappe.ui.form.on("Document Naming Settings", {
    transaction_type(frm) {
        show_gst_invoice_no_banner(frm);
    },
});

function show_gst_invoice_no_banner(frm) {
    frm.dashboard.clear_headline();
    if (
        !is_invoice_no_validation_required(
            frm.doc.transaction_type || frm.doc.document_type
        )
    )
        return;

    frm.dashboard.set_headline_alert(
        `GST Invoice Number cannot exceed 14 characters and
            should start with an alphanumeric character.
            It can only contain alphanumeric characters, dash (-) and slash (/).`,
        "blue"
    );
}

function is_invoice_no_validation_required(transaction_type) {
    return (
        transaction_type === "Sales Invoice" ||
        (transaction_type === "Purchase Invoice" &&
            gst_settings.enable_e_waybill_from_pi) ||
        (transaction_type === "Delivery Note" &&
            gst_settings.enable_e_waybill_from_dn) ||
        (transaction_type === "Purchase Receipt" &&
            gst_settings.enable_e_waybill_from_pr)
    );
}
