// Copyright (c) 2022, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("e-Waybill Log", {
    refresh: function (frm) {
        frm.add_custom_button(__("Fetch Latest"), () =>
            fetch_e_waybill_data(frm, { force: true }, () => {
                frm.refresh();
                frappe.show_alert(__("Latest e-Waybill fetched successfully"));
            })
        );
    },
});
