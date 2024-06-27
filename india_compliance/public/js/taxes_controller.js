frappe.provide("india_compliance");

const SUBCONTRACTING_DOCTYPE_ITEMS = [
    "Stock Entry Detail",
    "Subcontracting Order Item",
    "Subcontracting Receipt Item",
];

india_compliance.taxes_controller = class TaxesController {
    constructor(frm) {
        this.frm = frm;
        this.setup();
    }

    setup() {
        this.set_item_tax_template_query();
        this.set_account_head_query();
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

        if (!this.frm.doc.taxes || !this.frm.doc.taxes.length) return;

        let [items, taxes] = this.get_rows_to_update(item_name, tax_name);
        let tax_accounts = new Set(taxes.map(tax => tax.account_head));

        if (!tax_accounts.size) {
            return;
        }
        let tax_templates = new Set(items.map(item => item.item_tax_template));
        let item_tax_map = await this.get_item_tax_map(tax_templates, tax_accounts);

        let updated_taxes = [];
        for (let tax of taxes) {
            let item_wise_tax_rates = tax.item_wise_tax_rates
                ? JSON.parse(tax.item_wise_tax_rates)
                : {};

            for (let item of items) {
                let key = [item.item_tax_template, tax.account_head].toString();
                item_wise_tax_rates[item.name] = item_tax_map[key] || tax.rate;
            }

            tax.item_wise_tax_rates = JSON.stringify(item_wise_tax_rates);
            updated_taxes.push(tax);
        }
    }

    get_rows_to_update(item_name = null, tax_name = null) {
        /*
        Returns items and taxes to update based on itemName and taxName passed.
        If itemName and taxName are not passed, all items and taxes are returned.
        */
        let items = item_name
            ? this.frm.doc.items.filter(item => item.name === item_name)
            : this.frm.doc.items;
        let taxes = tax_name
            ? this.frm.doc.taxes.filter(tax => tax.name === tax_name)
            : this.frm.doc.taxes;

        return [items, taxes];
    }

    async get_item_tax_map(tax_templates, tax_accounts) {
        /**
         * Parameters:
         *     taxTemplates (Array): List of item tax templates used in the items
         *     taxAccounts (Array): List of tax accounts used in the taxes
         *
         * Returns:
         *     Object: A map of item_tax_template, tax_account and tax_rate
         *
         * Sample Output:
         *     {
         *         'GST 18%','IGST - TC': 18.0,
         *         'GST 28%','IGST - TC': 28.0
         *     }
         */

        if (!tax_templates.size) {
            return {};
        }

        let tax_rates = {};
        await frappe.call({
            method: "india_compliance.gst_india.utils.taxes_controller.get_item_tax_map",
            args: {
                tax_templates: Array.from(tax_templates),
                tax_accounts: Array.from(tax_accounts),
            },
            callback: function (r) {
                if (!r.exc) {
                    tax_rates = r.message;
                }
            },
        });

        return tax_rates;
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
        if (!row.charge_type || row.charge_type === "Actual") row.rate = 0;
        else {
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
            if (!row.charge_type || row.charge_type === "Actual") return;

            let tax_amount = 0;

            if (row.charge_type === "On Net Total") {
                tax_amount = this.get_tax_on_net_total(row);
            }
            if (row.charge_type == "On Item Quantity") {
                tax_amount = this.get_tax_on_item_quantity(row);
            }

            // update if tax amount is changed manually
            if (tax_amount !== row.tax_amount) {
                row.tax_amount = tax_amount;
            }

            if (
                frappe.flags.round_off_applicable_accounts?.includes(row.account_head)
            ) {
                row.tax_amount = Math.round(row.tax_amount);
            }
        });

        this.update_total_amount();
        this.update_total_taxes();
    }

    update_total_amount() {
        this.frm.doc.taxes.reduce((total, row) => {
            const total_amount = total + row.tax_amount;
            row.base_tax_amount_after_discount_amount = total_amount;

            return total_amount;
        }, 0);

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

    get_tax_on_item_quantity(tax_row) {
        /**
         * This method is used to calculate the tax amount on item quntity (cess non advol)
         * based on the item wise tax rates and item quantity.
         *
         * @param {object} tax_row - Tax row object.
         */

        const item_wise_tax_rates = JSON.parse(tax_row.item_wise_tax_rates || "{}");
        return this.frm.doc.items.reduce((total, item) => {
            return total + item.qty * item_wise_tax_rates[item.name];
        }, 0);
    }

    update_total_taxes() {
        const total_taxes = this.frm.doc.taxes.reduce(
            (total, row) => total + row.tax_amount,
            0
        );
        this.frm.set_value("total_taxes", total_taxes);
    }

    update_taxable_value(cdt, cdn) {
        const row = locals[cdt][cdn];
        let amount;

        // Function to calculate amount
        const calculateAmount = (qty, rate, precisionType) => {
            return flt(flt(qty) * flt(rate), precision(precisionType, row));
        };

        // TODO: rate is not updating before this method is called
        if (this.frm.doc.doctype === "Subcontracting Receipt") {
            amount = calculateAmount(row.qty, row.rate, "amount");
        } else if (this.frm.doc.doctype === "Stock Entry") {
            amount = calculateAmount(row.qty, row.basic_rate, "basic_amount");
        }

        row.taxable_value = amount;
    }
};

for (const doctype of SUBCONTRACTING_DOCTYPE_ITEMS) {
    frappe.ui.form.on(doctype, {
        async item_tax_template(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row.item_tax_template)
                frm.taxes_controller.update_item_wise_tax_rates();
            else await frm.taxes_controller.set_item_wise_tax_rates(cdn);
            frm.taxes_controller.update_tax_amount();
        },

        qty(frm, cdt, cdn) {
            frm.taxes_controller.update_taxable_value(cdt, cdn);
            frm.taxes_controller.update_tax_amount();
        },

        item_code(frm, cdt, cdn) {
            frm.taxes_controller.update_taxable_value(cdt, cdn);
            frm.taxes_controller.update_tax_amount();
        },
    });
}

frappe.ui.form.on("India Compliance Taxes and Charges", {
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
        if (!row.charge_type) {
            row.rate = 0;
            row.item_wise_tax_rates = "{}";
            frm.refresh_field("taxes");
        } else {
            await frm.taxes_controller.set_item_wise_tax_rates(null, cdn);
            frm.taxes_controller.update_tax_amount(cdt, cdn);
        }
    },
});

india_compliance.update_taxes = function (frm) {
    if (frm.doc.taxes_and_charges) {
        return frm.call({
            method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
            args: {
                master_doctype: frappe.meta.get_docfield(
                    frm.doc.doctype,
                    "taxes_and_charges",
                    frm.doc.name
                ).options,
                master_name: frm.doc.taxes_and_charges,
            },
            callback: function (r) {
                if (!r.exc) {
                    frm.set_value("taxes", r.message);
                }
            },
        });
    }
};
