const DOCTYPE = "Sales Invoice";

const erpnext_onload = frappe.listview_settings[DOCTYPE].onload;
frappe.listview_settings[DOCTYPE].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    setup_bulk_e_waybill_actions(DOCTYPE, list_view);
    setup_bulk_e_invoice_actions(DOCTYPE, list_view);
};
