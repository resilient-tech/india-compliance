// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bill of Entry", {
    onload(frm) {
        frm.bill_of_entry_controller = new BillOfEntryController(frm);
        if (frm.doc.items) frm.bill_of_entry_controller.update_total_taxable_value();
    },

    refresh(frm) {
        // disable add row button in items table
        frm.fields_dict.items.grid.wrapper.find(".grid-add-row").hide();
    },

    total_taxable_value(frm) {
        frm.taxes_controller.update_tax_amount();
    },

    total_customs_duty(frm) {
        frm.bill_of_entry_controller.update_total_amount_paid();
    },

    total_taxes(frm) {
        frm.bill_of_entry_controller.update_total_amount_paid();
    },
});

frappe.ui.form.on("Bill of Entry Item", {
    assessable_value: function (frm, cdt, cdn) {
        frm.bill_of_entry_controller.update_item_taxable_value(cdt, cdn);
    },
    customs_duty: function (frm, cdt, cdn) {
        frm.bill_of_entry_controller.update_item_taxable_value(cdt, cdn);
        frm.bill_of_entry_controller.update_total_customes_duty();
    },
});

frappe.ui.form.on("Bill of Entry Taxes", {
    rate: function (frm, cdt, cdn) {
        frm.taxes_controller.update_tax_rate(cdt, cdn);
    },
    tax_amount: function (frm, cdt, cdn) {
        frm.taxes_controller.update_tax_amount(cdt, cdn);
    },
});

class BillOfEntryController {
    constructor(frm) {
        this.frm = frm;
        this.frm.taxes_controller = new TaxesController(frm);
        this.setup();
    }

    setup() {
        this.set_account_query();
    }

    set_account_query() {
        ["paid_through_account", "customs_account"].forEach(field => {
            this.frm.set_query(field, () => {
                return {
                    filters: {
                        company: this.frm.doc.company,
                        is_group: 0,
                    },
                };
            });
        });
    }

    async update_item_taxable_value(cdt, cdn) {
        const row = locals[cdt][cdn];
        await frappe.model.set_value(
            cdt,
            cdn,
            "taxable_value",
            row.assessable_value + row.customs_duty
        );
        this.update_total_taxable_value();
    }

    update_total_taxable_value() {
        this.frm.set_value(
            "total_taxable_value",
            this.frm.doc.items.reduce((total, row) => {
                return total + row.taxable_value;
            }, 0)
        );
    }

    update_total_customes_duty() {
        this.frm.set_value(
            "total_customs_duty",
            this.frm.doc.items.reduce((total, row) => {
                return total + row.customs_duty;
            }, 0)
        );
    }

    update_total_taxes() {
        const total_taxes = this.frm.doc.taxes.reduce(
            (total, row) => total + row.tax_amount,
            0
        );
        console.log(total_taxes);
        this.frm.set_value("total_taxes", total_taxes);
    }

    update_total_amount_paid() {
        this.frm.set_value(
            "total_amount_paid",
            this.frm.doc.total_customs_duty + this.frm.doc.total_taxes
        );
    }
}

class TaxesController {
    constructor(frm, net_total_field) {
        this.frm = frm;
        this.net_total_field = net_total_field || "total_taxable_value";
        this.setup();
    }

    setup() {
        this.set_account_head_query();
    }

    set_account_head_query() {
        this.frm.set_query("account_head", "taxes", () => {
            return {
                filters: {
                    company: this.frm.doc.company,
                    is_group: 0,
                },
            };
        });
    }

    async update_tax_rate(cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.charge_type === "Actual") row.rate = 0;
        else if (row.charge_type === "On Net Total")
            await frappe.model.set_value(
                cdt,
                cdn,
                "tax_amount",
                this.get_tax_on_net_total(row)
            );
    }

    update_tax_amount(cdt, cdn) {
        let rows;
        if (cdt) rows = [locals[cdt][cdn]];
        else rows = this.frm.doc.taxes;

        rows.forEach(async row => {
            if (row.charge_type === "On Net Total") {
                const tax_amount = this.get_tax_on_net_total(row);

                // update if tax amount is changed manually
                if (tax_amount !== row.tax_amount) {
                    await frappe.model.set_value(
                        row.doctype,
                        row.name,
                        "tax_amount",
                        tax_amount
                    );
                }
            }
        });

        this.update_total_amount();
        this.frm.bill_of_entry_controller.update_total_taxes();
    }

    update_total_amount() {
        this.frm.doc.taxes.reduce((total, row) => {
            const total_amount = total + row.tax_amount;
            row.total = total_amount;

            return total_amount;
        }, this.frm.doc[this.net_total_field]);

        this.frm.refresh_field("taxes");
    }

    get_tax_on_net_total(row) {
        return (row.rate * this.frm.doc[this.net_total_field]) / 100;
    }
}
