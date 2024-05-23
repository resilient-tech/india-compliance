frappe.provide("india_compliance");

india_compliance.toggle_and_set_supply_liable_to = function (frm) {
    if (!gst_settings.enable_sales_through_ecommerce_operators) return;

    if (!frm.doc.ecommerce_gstin) {
        frm.set_value("supply_liable_to", "");
        return;
    }

    if (frm.doc.is_reverse_charge) {
        frm.set_value("supply_liable_to", "Reverse Charge u/s 9(5)");
    } else {
        frm.set_value("supply_liable_to", "Collect Tax u/s 52");
    }

}