// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on('e-Invoice Log', {
    refresh: function (frm) { },

    fetch_e_invoice_details: function (frm) {
        if (frm.doc.fetch_e_invoice_details) {
            frm.add_custom_button(__('Fetch E-Invoice Details'), function () {
                frappe.call({
                    method: "india_compliance.gst_india.utils.e_invoice.fetch_e_invoice_details",
                    args: {
                        "irn": frm.doc.irn,
                        "docname": frm.doc.reference_name,
                    },
                    callback: function () {
                        frm.reload_doc();
                    }
                });
            })
        }
        else {
            frm.remove_custom_button(__('Fetch E-Invoice Details'));
        }
    }
});
