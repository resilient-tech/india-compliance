frappe.ui.form.on("Purchase Invoice", {
    gst_category: function (frm) {
        if (
            gst_settings.require_supplier_invoice_no &&
            frm.doc.gst_category != "Unregistered"
        )
            frm.set_df_property("bill_no", "reqd", 1);
        else frm.set_df_property("bill_no", "reqd", 0);
    },
});
