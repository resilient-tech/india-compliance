frappe.provide("india_compliance");
frappe.provide("india_compliance.taxes_controller_events");

india_compliance.taxes_controller = class TaxesController {
    constructor(frm, field_map) {
        this.frm = frm;
        this.field_map = field_map || {};
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

    async process_tax_rate_update(cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.charge_type || row.charge_type === "Actual") row.rate = 0;
        else {
            this.update_item_wise_tax_rates(row);
            await this.update_tax_amount(cdt, cdn);
        }
    }

    update_taxes() {
        if (this.frm.doc.taxes_and_charges) {
            return frappe.call({
                method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
                args: {
                    master_doctype: frappe.meta.get_docfield(
                        this.frm.doc.doctype,
                        "taxes_and_charges",
                        this.frm.doc.name
                    ).options,
                    master_name: this.frm.doc.taxes_and_charges,
                },
                callback: async r => {
                    if (!r.exc) {
                        this.frm.set_value("taxes", r.message);
                        await this.set_item_wise_tax_rates();
                        this.update_tax_amount();
                    }
                },
            });
        }
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

    async set_item_wise_tax_rates(item_name, tax_name) {
        /**
         * This method is used to set item wise tax rates from the server
         * and update the item_wise_tax_rates field in the taxes table.
         *
         * @param {string} item_name - Item row name for which the tax rates are to be fetched.
         * @param {string} tax_name - Tax row name for which the tax rates are to be fetched.
         */

        if (!this.frm.doc.taxes || !this.frm.doc.taxes.length) return;

        await frappe.call({
            method: "india_compliance.gst_india.utils.taxes_controller.set_item_wise_tax_rates",
            args: {
                doc: this.frm.doc,
                item_name: item_name,
                tax_name: tax_name,
            },
        });
    }

    update_item_taxable_value(cdt, cdn) {
        const row = locals[cdt][cdn];
        let amount;

        // Function to calculate amount
        const calculateAmount = (qty, rate, precisionType) => {
            return flt(flt(qty) * flt(rate), precision(precisionType, row));
        };

        if (this.frm.doc.doctype === "Subcontracting Receipt") {
            amount = calculateAmount(row.qty, row.rate, "amount");
        } else if (this.frm.doc.doctype === "Stock Entry") {
            amount = calculateAmount(row.qty, row.basic_rate, "basic_amount");
        }

        row.taxable_value = amount;
    }

    async update_tax_amount() {
        /**
         * This method is used to update the tax amount in the tax rows
         */

        let total_taxes = 0;
        const total_taxable_value = this.calculate_total_taxable_value();

        this.frm.doc.taxes.forEach(async row => {
            if (!row.charge_type || row.charge_type === "Actual") return;

            row.tax_amount = this.get_tax_amount(row);

            if (frappe.flags.round_off_applicable_accounts?.includes(row.account_head))
                row.tax_amount = Math.round(row.tax_amount);

            total_taxes += row.tax_amount;
            row.base_total = total_taxes + total_taxable_value;
        });

        this.frm.set_value(this.get_fieldname("total_taxes"), total_taxes);
        this.update_base_grand_total();
        this.frm.refresh_field("taxes");
    }

    update_base_grand_total() {
        const grand_total =
            this.calculate_total_taxable_value() + this.get_value("total_taxes");
        this.frm.set_value(this.get_fieldname("base_grand_total"), grand_total);
    }

    get_tax_amount(tax_row) {
        /**
         * Calculate tax amount based on the charge type.
         */

        const item_wise_tax_rates = JSON.parse(tax_row.item_wise_tax_rates || "{}");
        return this.frm.doc.items.reduce((total, item) => {
            let multiplier =
                item.charge_type === "On Item Quantity"
                    ? item.qty
                    : item.taxable_value / 100;
            return (
                total + multiplier * (item_wise_tax_rates[item.name] || tax_row.rate)
            );
        }, 0);
    }

    calculate_total_taxable_value() {
        return this.frm.doc.items.reduce((total, item) => {
            return total + item.taxable_value;
        }, 0);
    }

    get_value(field, doc, default_value) {
        if (!default_value) default_value = 0;
        doc = doc || this.frm.doc;

        if (this.field_map[field]) return doc[this.field_map[field]] || default_value;

        return doc[field] || default_value;
    }

    get_fieldname(field) {
        return this.field_map[field] || field;
    }
};

Object.assign(india_compliance.taxes_controller_events, {
    async item_tax_template(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_tax_template) frm.taxes_controller.update_item_wise_tax_rates();
        else await frm.taxes_controller.set_item_wise_tax_rates(cdn);
        frm.taxes_controller.update_tax_amount();
    },

    qty(frm, cdt, cdn) {
        frm.taxes_controller.update_item_taxable_value(cdt, cdn);
        frm.taxes_controller.update_tax_amount();
    },

    item_code(frm, cdt, cdn) {
        frm.taxes_controller.update_item_taxable_value(cdt, cdn);
        frm.taxes_controller.update_tax_amount();
    },

    items_remove(frm) {
        frm.taxes_controller.update_tax_amount();
    },
});

frappe.ui.form.on("India Compliance Taxes and Charges", {
    rate(frm, cdt, cdn) {
        frm.taxes_controller.process_tax_rate_update(cdt, cdn);
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
