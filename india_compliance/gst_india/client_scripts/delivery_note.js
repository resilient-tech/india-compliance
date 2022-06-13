{% include "india_compliance/gst_india/client_scripts/taxes.js" %}

const DOCTYPE = "Delivery Note";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
update_gst_vehicle_type(DOCTYPE);
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });
    },
    validate(frm) {
        let settings = frappe.boot.gst_settings;
        if (
            frm.doc.docstatus ||
            frm.doc.customer_address ||
            !(settings.enable_e_waybill && settings.enable_e_waybill_from_dn)
        )
            return;

        frappe.show_alert({
            message: __("Customer Address is required to generate e-Waybill from Delivery Note"),
            indicator: "yellow",
        });
    },
});
