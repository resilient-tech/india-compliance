frappe.provide("india_compliance");

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

        if (!this.frm.taxes || !this.frm.taxes.length) return;

        //TODO:
        await this.frm.call(
            "india_compliance.gst_india.utils.taxes_controller.TaxesController.set_item_wise_tax_rates",
            {
                item_name: item_name,
                tax_name: tax_name,
            }
        );
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
};
