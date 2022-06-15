{% include "india_compliance/gst_india/client_scripts/transaction.js" %}

const DOCTYPE = "Delivery Note";

setup_e_waybill_actions(DOCTYPE);
setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
validate_overseas_gst_category(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });
    },
    after_save(frm) {
        const { gst_settings } = frappe.boot;
        if (
            frm.doc.docstatus ||
            frm.doc.customer_address ||
            !(gst_settings.enable_e_waybill && gst_settings.enable_e_waybill_from_dn)
        )
            return;

        frappe.show_alert({
            message: __("Billing Address is required to create e-Waybill"),
            indicator: "yellow",
        }, 10);
    },
});
