// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on('e-Invoice Log', {
    refresh: function (frm) {
        if (!frm.doc.invoice_data) {
            frm.add_custom_button(__('Fetch e-Invoice Details'), () => fetch_e_invoice_details(frm));
        }
    },
});

function fetch_e_invoice_details(frm) {
    taxpayer_api.call({
        method: "india_compliance.gst_india.utils.e_invoice.mark_e_invoice_as_generated",
        args: {
            "doctype": frm.doc.reference_doctype,
            "docname": frm.doc.reference_name,
            "values": {"irn" : frm.doc.irn, "fetch_invoice_details": 1}
        },
        callback: function () {
            frm.reload_doc();
        }
    });
}
