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

    async company(frm) {
        if (!frm.doc.company) {
            frm.set_value("company_gstin", "");
            return;
        }

        const options = await india_compliance.set_gstin_options(frm);
        frm.set_value("company_gstin", options[0]);

        const { message } = await frappe.db.get_value("Company", frm.doc.company, [
            "default_customs_payable_account as customs_payable_account",
            "default_customs_expense_account as customs_expense_account",
        ]);

        frm.set_value(message);
    },

    get_items_from_purchase_invoice(frm) {
        if (!(frm.doc.company && frm.doc.company_gstin)) {
            frappe.msgprint(__("Please Select Company and Company GSTIN First"));
            return;
        }

        const d = new frappe.ui.form.MultiSelectDialog({
            doctype: "Purchase Invoice",
            target: frm,
            setters: {
                company: frm.doc.company,
                company_gstin: frm.doc.company_gstin,
            },
            read_only_setters: ["company", "company_gstin"],
            get_query() {
                return {
                    query: "india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry.fetch_pending_boe_invoices",
                };
            },
            add_filters_group: 1,
            action: function (selections, args) {
                if (selections.length === 0) {
                    frappe.msgprint(
                        __("Please select at least one Purchase Invoice"),
                        __("No Selection")
                    );
                    return;
                }

                frm.call("get_items_from_purchase_invoice", {
                    purchase_invoices: selections,
                }).then(d.dialog.hide());
            },
        });
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

class BillOfEntryController {
    constructor(frm) {
        this.frm = frm;
        this.frm.taxes_controller = new india_compliance.taxes_controller(frm);
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

    update_total_amount_payable() {
        this.frm.set_value(
            "total_amount_payable",
            this.frm.doc.total_customs_duty + this.frm.doc.total_taxes
        );
    }
}
