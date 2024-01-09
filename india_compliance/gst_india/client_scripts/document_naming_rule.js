{% include "india_compliance/gst_india/client_scripts/document_naming_settings.js" %}


frappe.ui.form.on("Document Naming Rule", {
    document_type(frm) {
        show_gst_invoice_no_banner(frm);
    },
});
