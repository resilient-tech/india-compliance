const DOCTYPE = "Sales Order";

frappe.ui.form.on(DOCTYPE, {
    is_reverse_charge(frm) {
        if (frm.doc.ecommerce_gstin) {
            set_supply_liable_to(frm)
        }
    },
    ecommerce_gstin(frm) {
        if (!frm.doc.ecommerce_gstin) {
            frm.set_value("supply_liable_to", "")
            frm.set_df_property("supply_liable_to", "hidden", 1)

        }
        else {
            frm.set_df_property("supply_liable_to", "hidden", 0)
            set_supply_liable_to(frm)
        }

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