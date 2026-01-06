// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("e-Waybill Log", {
    refresh: function (frm) {
        frm.add_custom_button(__("Fetch Latest"), () =>
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.fetch_e_waybill_data",
                args: { doctype: frm.doctype, docname: frm.doc.name, force: true },
                callback: () => {
                    frm.refresh();
                    frappe.show_alert(__("Latest e-Waybill fetched successfully"));
                },
            })
        );
    },
});
