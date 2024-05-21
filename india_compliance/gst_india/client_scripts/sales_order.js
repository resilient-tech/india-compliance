const DOCTYPE = "Sales Order";

frappe.ui.form.on(DOCTYPE, {
    is_reverse_charge(frm) {
        india_compliance.toggle_and_set_supply_liable_to(frm)
    },
    ecommerce_gstin(frm) {
        india_compliance.toggle_and_set_supply_liable_to(frm)
    }
})
