frappe.require("assets/india_compliance/js/transaction.js");

frappe.ui.form.on("Document Naming Rule", {
    document_type(frm) {
        show_gst_invoice_no_banner(frm);
    },
});
