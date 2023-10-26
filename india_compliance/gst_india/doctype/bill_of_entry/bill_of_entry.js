// Copyright (c) 2023, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bill of Entry", {
    onload(frm) {
        frm.fields_dict.items.grid.cannot_add_rows = true;
        frm.bill_of_entry_controller = new BillOfEntryController(frm);
    },

    refresh(frm) {
        india_compliance.set_reconciliation_status(frm, "bill_of_entry_no");

        if (frm.doc.docstatus === 0) return;

        // check if Journal Entry exists;
        if (frm.doc.docstatus === 1 && !frm.doc.__onload?.journal_entry_exists) {
            frm.add_custom_button(
                __("Journal Entry for Payment"),
                () => {
                    frappe.model.open_mapped_doc({
                        method: "india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry.make_journal_entry_for_payment",
                        frm: frm,
                    });
                },
                __("Create")
            );
        }

        const has_ineligible_items = frm.doc.items.some(
            item => item.is_ineligible_for_itc
        );

        if (
            (frm.doc.docstatus === 1 && frm.doc.total_customs_duty > 0) ||
            has_ineligible_items
        ) {
            frm.add_custom_button(
                __("Landed Cost Voucher"),
                () => {
                    frappe.model.open_mapped_doc({
                        method: "india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry.make_landed_cost_voucher",
                        frm: frm,
                    });
                },
                __("Create")
            );
        }

        frm.add_custom_button(
            __("Accounting Ledger"),
            () => {
                frappe.route_options = {
                    voucher_no: frm.doc.name,
                    from_date: frm.doc.posting_date,
                    to_date: frm.doc.posting_date,
                    company: frm.doc.company,
                    group_by: "Group by Voucher (Consolidated)",
                    show_cancelled_entries: frm.doc.docstatus === 2,
                };
                frappe.set_route("query-report", "General Ledger");
            },
            __("View")
        );
    },

    total_taxable_value(frm) {
        frm.taxes_controller.update_tax_amount();
    },

    total_customs_duty(frm) {
        frm.bill_of_entry_controller.update_total_amount_payable();
    },

    total_taxes(frm) {
        frm.bill_of_entry_controller.update_total_amount_payable();
    },
});

frappe.ui.form.on("Bill of Entry Item", {
    assessable_value(frm, cdt, cdn) {
        frm.bill_of_entry_controller.update_item_taxable_value(cdt, cdn);
    },

    customs_duty(frm, cdt, cdn) {
        frm.bill_of_entry_controller.update_item_taxable_value(cdt, cdn);
        frm.bill_of_entry_controller.update_total_customs_duty();
    },

    async item_tax_template(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_tax_template) frm.taxes_controller.update_item_wise_tax_rates();
        else await frm.taxes_controller.set_item_wise_tax_rates(cdn);

        frm.taxes_controller.update_tax_amount();
    },

    items_remove(frm) {
        frm.bill_of_entry_controller.update_total_taxable_value();
    },
});

frappe.ui.form.on("Bill of Entry Taxes", {
    rate(frm, cdt, cdn) {
        frm.taxes_controller.update_tax_rate(cdt, cdn);
    },

    tax_amount(frm, cdt, cdn) {
        frm.taxes_controller.update_tax_amount(cdt, cdn);
    },

    async account_head(frm, cdt, cdn) {
        await frm.taxes_controller.set_item_wise_tax_rates(null, cdn);
        frm.taxes_controller.update_tax_amount(cdt, cdn);
    },

    async charge_type(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.charge_type === "On Net Total") {
            await frm.taxes_controller.set_item_wise_tax_rates(null, cdn);
            frm.taxes_controller.update_tax_amount(cdt, cdn);
        } else {
            row.rate = 0;
            row.item_wise_tax_rates = "{}";
            frm.refresh_field("taxes");
        }
    },

    taxes_remove(frm) {
        frm.bill_of_entry_controller.update_total_taxes();
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
        [
            {
                name: "customs_payable_account",
                filters: { root_type: "Liability", account_type: ["!=", "Payable"] },
            },
            { name: "customs_expense_account", filters: { root_type: "Expense" } },
            { name: "cost_center" },
        ].forEach(row => {
            this.frm.set_query(row.name, () => {
                return {
                    filters: {
                        ...row.filters,
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

    update_total_customs_duty() {
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
        this.frm.set_value("total_taxes", total_taxes);
    }

    update_total_amount_payable() {
        this.frm.set_value(
            "total_amount_payable",
            this.frm.doc.total_customs_duty + this.frm.doc.total_taxes
        );
    }
}

class TaxesController {
    constructor(frm) {
        this.frm = frm;
        this.setup();
    }

    setup() {
        this.fetch_round_off_accounts();
        this.set_item_tax_template_query();
        this.set_account_head_query();
    }

    fetch_round_off_accounts() {
        if (this.frm.doc.docstatus !== 0 || !this.frm.doc.company) return;

        frappe.call({
            method: "erpnext.controllers.taxes_and_totals.get_round_off_applicable_accounts",
            args: {
                company: this.frm.doc.company,
                account_list: [],
            },
            callback(r) {
                if (r.message) {
                    frappe.flags.round_off_applicable_accounts = r.message;
                }
            },
        });
    }

    set_item_tax_template_query() {
        this.frm.set_query("item_tax_template", "items", () => {
            return {
                filters: {
                    company: this.frm.doc.company,
                },
            };
        });
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

    async set_item_wise_tax_rates(item_name, tax_name) {
        /**
         * This method is used to set item wise tax rates from the server
         * and update the item_wise_tax_rates field in the taxes table.
         *
         * @param {string} item_name - Item row name for which the tax rates are to be fetched.
         * @param {string} tax_name - Tax row name for which the tax rates are to be fetched.
         */

        if (!this.frm.taxes || !this.frm.taxes.length) return;

        await this.frm.call("set_item_wise_tax_rates", {
            item_name: item_name,
            tax_name: tax_name,
        });
    }

    update_item_wise_tax_rates(tax_row) {
        /**
         * This method is used to update the item_wise_tax_rates field in the taxes table when
         * - Item tax template is removed from the item row.
         * - Tax rate is changed in the tax row.
         *
         * It will update item rate with default tax rate.
         *
         * @param {object} tax_row - Tax row object.
         */

        let taxes;
        if (tax_row) taxes = [tax_row];
        else taxes = this.frm.doc.taxes;

        taxes.forEach(tax => {
            const item_wise_tax_rates = JSON.parse(tax.item_wise_tax_rates || "{}");
            this.frm.doc.items.forEach(item => {
                if (item.item_tax_template) return;
                item_wise_tax_rates[item.name] = tax.rate;
            });
            tax.item_wise_tax_rates = JSON.stringify(item_wise_tax_rates);
        });
    }

    async update_tax_rate(cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.charge_type === "Actual") row.rate = 0;
        else if (row.charge_type === "On Net Total") {
            this.update_item_wise_tax_rates(row);
            await this.update_tax_amount(cdt, cdn);
        }
    }

    async update_tax_amount(cdt, cdn) {
        /**
         * This method is used to update the tax amount in the tax row
         * - Update for all tax rows when cdt is null.
         * - Update for a single tax row when cdt and cdn are passed.
         *
         * @param {string} cdt - DocType of the tax row.
         * @param {string} cdn - Name of the tax row.
         */

        let taxes;
        if (cdt) taxes = [locals[cdt][cdn]];
        else taxes = this.frm.doc.taxes;

        taxes.forEach(async row => {
            if (row.charge_type !== "On Net Total") return;

            const tax_amount = this.get_tax_on_net_total(row);

            // update if tax amount is changed manually
            if (tax_amount !== row.tax_amount) {
                row.tax_amount = tax_amount;
            }

            if (frappe.flags.round_off_applicable_accounts?.includes(row.account_head)) {
                row.tax_amount = Math.round(row.tax_amount);
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
        }, this.frm.doc.total_taxable_value);

        this.frm.refresh_field("taxes");
    }

    get_tax_on_net_total(tax_row) {
        /**
         * This method is used to calculate the tax amount on net total
         * based on the item wise tax rates.
         *
         * @param {object} tax_row - Tax row object.
         */

        const item_wise_tax_rates = JSON.parse(tax_row.item_wise_tax_rates || "{}");
        return this.frm.doc.items.reduce((total, item) => {
            return total + (item.taxable_value * item_wise_tax_rates[item.name]) / 100;
        }, 0);
    }
}
