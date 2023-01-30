// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bill of Entry", {
    onload(frm) {
        hide_unrequired_fields(frm);
    },
    refresh: function (frm) {
        frm.fields_dict.items.grid.wrapper.find(".grid-add-row").hide();
    },
    update_taxable_value: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        frappe.model.set_value(
            cdt,
            cdn,
            "taxable_value",
            row.assessable_value + row.customs_duty
        );
        frm.events.update_total_taxable_value(frm);
    },
    update_total_taxable_value: function (frm) {
        frm.set_value(
            "total_taxable_value",
            frm.doc.items.reduce((total, row) => {
                return total + row.taxable_value;
            }, 0)
        );
    },
    update_total_customes_duty: function (frm) {
        frm.set_value(
            "total_customs_duty",
            frm.doc.items.reduce((total, row) => {
                return total + row.customs_duty;
            }, 0)
        );
    },
});

frappe.ui.form.on("Bill of Entry Item", {
    assessable_value: function (frm, cdt, cdn) {
        frm.events.update_taxable_value(frm, cdt, cdn);
    },
    customs_duty: function (frm, cdt, cdn) {
        frm.events.update_taxable_value(frm, cdt, cdn);
        frm.events.update_total_customes_duty(frm, cdt, cdn);
    },
});

function setup_taxes(frm) {
    if (!frm.doc.taxes) return;
    frm.doc.taxes.forEach(row => {
        frm.set_df_property("taxes", "read_only", 1, row.name, "category");
    });
}

function hide_unrequired_fields(frm) {
    const unreuired_fields = ["category", "add_deduct_tax", "included_in_print_rate"];

    unreuired_fields.forEach(field => {
        frappe.meta.get_docfield(
            "Purchase Taxes and Charges",
            field,
            frm.doc.name
        ).hidden = 1;
    });
}
