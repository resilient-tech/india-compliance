// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("e-Waybill Log", {
    refresh: function (frm) {
        frm.add_custom_button(__("Fetch Latest"), () =>
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.fetch_e_waybill_data",
                args: { doctype: frm.doctype, docname: frm.doc.name, force: true },
                freeze: true,
                freeze_message: __("Fetching latest e-Waybill data..."),
                callback: () => {
                    frm.refresh();
                    frappe.show_alert(__("Latest e-Waybill fetched successfully"));
                },
                error: error => {
                    console.error(error);
                    frappe.show_alert(__("Failed to fetch latest e-Waybill data"));
                },
            })
        );
    },
});
