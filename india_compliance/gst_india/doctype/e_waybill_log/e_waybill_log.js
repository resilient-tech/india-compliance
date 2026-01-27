// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("e-Waybill Log", {
    refresh: function (frm) {
        frm.add_custom_button(__("Fetch Latest Data"), () =>
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.fetch_e_waybill_data",
                args: {
                    doctype: frm.doc.reference_doctype,
                    docname: frm.doc.reference_name,
                    force: true,
                },
                freeze: true,
                freeze_message: __("Fetching latest e-Waybill data..."),
                callback: () => {
                    frm.refresh();
                    frappe.show_alert(__("Latest e-Waybill data fetched successfully"));
                },
            })
        );
    },
});
