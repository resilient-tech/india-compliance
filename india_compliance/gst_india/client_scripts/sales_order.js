const DOCTYPE = "Sales Order";

frappe.ui.form.on(DOCTYPE, {
    is_reverse_charge(frm) {
        india_compliance.toggle_and_set_supply_liable_to(frm)
    },
    ecommerce_gstin(frm) {
        india_compliance.toggle_and_set_supply_liable_to(frm)
    }
})

function set_supply_liable_to(frm) {
    if (frm.doc.is_reverse_charge) {
        frm.set_value("supply_liable_to", "Reverse Charge u/s 9(5)")
    }
    else {
        frm.set_value("supply_liable_to", "Collect Tax u/s 52")
    }
}