const IMPORT_GST_CATEGORIES = ["Overseas", "SEZ"];

frappe.ui.form.on("ISD Invoice", {
    setup(frm) {
        frm.isd_controller = new ISDInvoiceController(frm);
    },

    refresh(frm) {
        frm.set_df_property("to_party_state", "options", [""].concat(frappe.boot.india_state_options));
        frm.isd_controller.update_address_labels();        // Show button to create inter-company invoice on submit
        if (frm.doc.docstatus === 1 && frm.doc.is_against_party && !frm.doc.inter_company_invoice_reference) {
            frm.add_custom_button(
                __("Inter Company ISD Invoice"),
                () => {
                    frappe.model.open_mapped_doc({
                        method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.create_inter_company_invoice",
                        frm: frm,
                    });
                },
                __("Create"),
            );
        }

    },

    company(frm) {
        frm.set_value("is_against_party", 0);
        frm.isd_controller.fetchGSTAccounts();
        frm.isd_controller.autofill_addresses();
    },

    is_against_party(frm) {
        if (!frm.doc.is_against_party) {
            // frm.set_value("party_type", null);
            // frm.set_value("party", null);
            // frm.set_value("credit_flow", null);
            // frm.set_value("party_account", null);
        } else {
            frm.set_value("credit_flow", "Outward");
            frm.trigger("credit_flow"); // above trigger does not work first time
        }
    },

    credit_flow(frm) {
        frm.isd_controller.update_address_labels();
        frm.isd_controller.autofill_addresses();
        frm.isd_controller.autofill_party_account();
    },

    party_type(frm) {
        if (frm.doc.is_against_party) {
            frm.isd_controller.update_party_label();
            frm.isd_controller.autofill_party();
        }
    },

    party(frm) {
        if (frm.doc.is_against_party && frm.doc.party) {
            frm.isd_controller.autofill_addresses_for_party();
        }
    },

    distribution_ratio(frm) {
        if (frm.doc.distribution_ratio < 0 || frm.doc.distribution_ratio > 100) {
            frappe.show_alert({
                message: __("Distribution ratio must be between 0 and 100"),
                indicator: "red",
            });
            return;
        }

        frm.isd_controller.recalculate();
    },

    company_address(frm) {
        frm.isd_controller.set_address_display("company_address", "company_address_display");
        frm.isd_controller.recalculate();
    },

    party_address(frm) {
        frm.isd_controller.set_address_display("party_address", "party_address_display");
        frm.isd_controller.recalculate();
    },

    get_purchase_invoices(frm) {
        const d = new frappe.ui.form.MultiSelectDialog({
            doctype: "Purchase Invoice",
            target: frm,
            primary_action_label: __("Get Purchase Invoices"),
            setters: {
                company: frm.doc.company,
            },
            read_only_setters: ["company"],
            data_fields: [
                {
                    fieldtype: "Float",
                    label: __("Distribution Ratio (%)"),
                    fieldname: "distribution_ratio",
                    default: frm.doc.distribution_ratio || 0.0,
                },
                {
                    fieldtype: "Column Break",
                    fieldname: "cb1",
                },
            ],
            get_query() {
                return {
                    filters: {
                        docstatus: 1,
                        company: frm.doc.company,
                        billing_address: frm.doc.company_address,
                        company_gstin: frm.doc.company_gstin,
                        is_isd_applicable: 1,
                    },
                };
            },
            add_filters_group: 1,
            action: (selections, data) => {
                if (selections.length === 0) {
                    frappe.msgprint(__("Please select at least one Purchase Invoice"), __("No Selection"));
                    return;
                }

                // set the distribution ratio value silently (without triggering the field event)
                if (!frm.doc.distribution_ratio) {
                    frm.doc.distribution_ratio = data.distribution_ratio || 0.0;
                }

                frm.call("get_purchase_invoices", {
                    purchase_invoices: selections,
                    distribution_ratio: data.distribution_ratio || 0.0,
                }).then(() => {
                    d.dialog.hide();
                    frm.isd_controller.recalculate();
                });
            },
        });

        // Move distribution_ratio section before the results area.
        // rearrangement runs after the make is complete
        const rearrange = () => {
            const $dist = d.dialog?.fields_dict?.distribution_ratio?.$wrapper?.closest(".form-section");
            const $results = d.dialog?.fields_dict?.results_area?.$wrapper?.closest(".form-section");
            if ($dist && $results) $dist.insertBefore($results);
        };

        if (d.dialog) {
            // doctype was already cached — dialog already built
            rearrange();
        } else {
            // monkey patch make() to avoid fields_dict not ready issue
            const _make = d.make.bind(d);
            d.make = function () {
                _make();
                rearrange();
            };
        }
    },
});

frappe.ui.form.on("ISD Invoice Source Item", {
    source_invoices_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "distribution_ratio", frm.doc.distribution_ratio || 0);
    },
    purchase_invoice(frm, cdt, cdn) {
        if (!(frm.is_against_party && frm.doc.credit_flow == "Inward")) {
            frm.isd_controller.autofill_source_item(cdt, cdn);
        }
    },
    is_ineligible_for_itc(frm, cdt, cdn) {
        frm.isd_controller.autofill_source_item(cdt, cdn);
    },

    distribution_ratio(frm) {
        frm.isd_controller.recalculate();
    },
});

class ISDInvoiceController {
    constructor(frm) {
        this.frm = frm;
        this.setup();
    }

    setup() {
        this.set_queries();
    }

    set_queries() {
        this.frm.set_query("company_address", () => {
            if (!this.frm.doc.company) {
                frappe.show_alert({
                    message: __("Please set Company first"),
                    indicator: "orange",
                });
                return { filters: {} };
            }
            const is_company_recipient =
                this.frm.doc.is_against_party && this.frm.doc.credit_flow === "Inward";
            const filters = {
                link_doctype: "Company",
                link_name: this.frm.doc.company,
            };
            // Only filter by gst_category for equality; skip the != case
            if (!is_company_recipient) {
                filters.gst_category = "Input Service Distributor";
            }
            return {
                query: "frappe.contacts.doctype.address.address.address_query",
                filters,
            };
        });

        this.frm.set_query("party_type", () => {
            if (!this.frm.doc.is_against_party) {
                return { filters: { name: ["in", ["Company"]] } };
            }
            return { filters: { name: ["in", ["Supplier", "Customer"]] } };
        });

        this.frm.set_query("party_address", () => {
            // for single company setup
            if (!this.frm.doc.is_against_party) {
                return {
                    query: "frappe.contacts.doctype.address.address.address_query",
                    filters: {
                        link_doctype: "Company",
                        link_name: this.frm.doc.company,
                    },
                };
            }

            // for multi company setup
            if (!this.frm.doc.party || !this.frm.doc.party_type) {
                frappe.show_alert({
                    message: __("Please set Party Type and Party Name first"),
                    indicator: "orange",
                });
                return { filters: {} };
            }

            const filters = {
                link_doctype: this.frm.doc.party_type,
                link_name: this.frm.doc.party,
            };

            if (this.frm.doc.credit_flow === "Inward") {
                filters.gst_category = "Input Service Distributor";
            }

            return {
                query: "frappe.contacts.doctype.address.address.address_query",
                filters,
            };
        });

        this.frm.set_query("account_head", "taxes", () => {
            return {
                filters: {
                    company: this.frm.doc.company,
                    is_group: 0,
                },
            };
        });

        this.frm.set_query("purchase_invoice", "source_invoices", () => {
            return {
                query: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.search_purchase_invoice",
                params: {
                    company: this.frm.doc.company,
                    billing_address: this.frm.doc.company_address,
                },
            };
        });

        this.frm.set_query("party_account", () => {
            const account_type = this.frm.doc.credit_flow === "Inward" ? "Receivable" : "Payable";
            return {
                filters: {
                    company: this.frm.doc.company,
                    account_type: account_type,
                    is_group: 0,
                },
            };
        });
    }

    autofill_party_account() {
        if (!this.frm.doc.company || !this.frm.doc.credit_flow || !this.frm.doc.is_against_party) return;

        const account_field =
            this.frm.doc.credit_flow === "Outward" ? "default_payable_account" : "default_receivable_account";

        frappe.db.get_value("Company", this.frm.doc.company, account_field).then((result) => {
            this.frm.set_value("party_account", result.message?.[account_field]);
        });
    }

    autofill_addresses() {
        /**
         * Shared entry point for is_against_party and credit_flow changes.
         * Single company: autofills addresses directly.
         * Multi company: sets party_type → triggers cascade:
         *   party_type event → autofill_party → party event → autofill_addresses_for_party
         */

        if (!this.frm.doc.is_against_party) {
            this.autofill_addresses_single_company();
            return;
        }

        const party_type = this.frm.doc.credit_flow === "Outward" ? "Customer" : "Supplier";
        this.frm.set_value("party_type", party_type);
        // Event chain handles the rest:
        //   party_type event → autofill_party → party event → autofill_addresses_for_party
    }

    async _get_address(link_doctype, link_name, extra_filters = []) {
        const results = await frappe.db.get_list("Address", {
            filters: [
                ["disabled", "=", 0],
                ["Dynamic Link", "link_doctype", "=", link_doctype],
                ["Dynamic Link", "link_name", "=", link_name],
                ...extra_filters,
            ],
            fields: ["name"],
            limit: 1,
        });
        return results[0]?.name || null;
    }

    autofill_addresses_single_company() {
        if (!this.frm.doc.company) return;

        Promise.all([
            this._get_address("Company", this.frm.doc.company, [
                ["gst_category", "=", "Input Service Distributor"],
            ]),
            this._get_address("Company", this.frm.doc.company, [
                ["gst_category", "!=", "Input Service Distributor"],
            ]),
        ]).then(([company_address, party_address]) => {
            this.frm.set_value("company_address", company_address);
            this.frm.set_value("party_address", party_address);
        });
    }

    autofill_party() {
        /** Set party to the first internal customer/supplier based on party_type. */
        if (!this.frm.doc.party_type) return;

        const is_customer = this.frm.doc.party_type === "Customer";
        frappe.db
            .get_list(this.frm.doc.party_type, {
                filters: { [is_customer ? "is_internal_customer" : "is_internal_supplier"]: 1 },
                fields: ["name"],
                limit: 1,
            })
            .then((results) => {
                this.frm.set_value("party", results[0]?.name || null);
            });
    }

    autofill_addresses_for_party() {
        if (!this.frm.doc.company || !this.frm.doc.party || !this.frm.doc.party_type) return;

        const is_outward = this.frm.doc.credit_flow === "Outward";

        Promise.all([
            this._get_address("Company", this.frm.doc.company, [
                ["gst_category", is_outward ? "=" : "!=", "Input Service Distributor"],
            ]),
            this._get_address(
                this.frm.doc.party_type,
                this.frm.doc.party,
                !is_outward ? [["gst_category", "=", "Input Service Distributor"]] : [],
            ),
        ]).then(([company_address, party_address]) => {
            this.frm.set_value("company_address", company_address);
            this.frm.set_value("party_address", party_address);
        });
    }

    update_party_label() {
        const party_type = this.frm.doc.party_type;
        this.frm.set_df_property("party", "label", party_type);
        this.frm.refresh_field("party");
    }

    update_address_labels() {
        const LABELS = {
            default: {
                company_address: __("Select Company Address"),
                party_address: __("Select Party Address"),
            },
            Outward: {
                company_address: __("Select Company Address (Distributor)"),
                party_address: __("Select Party Address (Recipient)"),
            },
            Inward: {
                company_address: __("Select Company Address (Recipient)"),
                party_address: __("Select Party Address (Distributor)"),
            },
        };

        const key = !this.frm.doc.is_against_party ? "default" : this.frm.doc.credit_flow || "Inward";
        const labels = LABELS[key] || LABELS.Inward;

        this.frm.set_df_property("company_address", "label", labels.company_address);
        this.frm.set_df_property("party_address", "label", labels.party_address);
        this.frm.refresh_field("company_address");
        this.frm.refresh_field("party_address");
    }

    autofill_source_item(cdt, cdn) {

        const row = locals[cdt][cdn];
        if (!row.purchase_invoice) return;

        frappe
            .call({
                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_source_invoices_from_purchase_invoices",
                args: { purchase_invoices: [row.purchase_invoice] },
                callback: (result) => {
                    const items = result.message || [];
                    const match = items.find((item) => item.is_ineligible_for_itc == row.is_ineligible_for_itc);
                    if (!match) {
                        const itc_type = row.is_ineligible_for_itc ? __("ineligible") : __("eligible");
                        frappe.msgprint({
                            message: __("No {0} ITC taxes found for Purchase Invoice {1}", [
                                itc_type,
                                row.purchase_invoice,
                            ]),
                            indicator: "orange",
                            title: __("No Matching Taxes"),
                        });
                        frappe.model.set_value(cdt, cdn, {
                            total_igst: 0,
                            total_cgst: 0,
                            total_sgst: 0,
                            total_cess: 0,
                            total_cess_non_advol: 0,
                        });
                        return;
                    }
    
                    frappe.model.set_value(cdt, cdn, {
                        total_igst: match.total_igst,
                        total_cgst: match.total_cgst,
                        total_sgst: match.total_sgst,
                        total_cess: match.total_cess,
                        total_cess_non_advol: match.total_cess_non_advol,
                    });
                    this.recalculate();
                }
            })
    }

    set_address_display(address_field, display_field) {
        const address = this.frm.doc[address_field];
        if (address) {
            frappe
                .call({
                    method: "frappe.contacts.doctype.address.address.get_address_display",
                    args: { address_dict: address },
                })
                .then((response) => {
                    this.frm.set_value(display_field, response.message || "");
                });
        } else {
            this.frm.set_value(display_field, "");
        }
    }

    // TODO: optimize this

    fetchGSTAccounts() {
        if (!this.frm.doc.company) return;
        frappe
            .call({
                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_input_gst_accounts",
                args: { company: this.frm.doc.company },
            })
            .then((result) => {
                this.gst_accounts = result.message || {};
            });
    }

    async is_inter_state_distribution() {
        const { company_pos, party_pos, company_address, party_address } = this.frm.doc;

        if (company_pos && party_pos && company_pos !== party_pos) return true;

        for (const address of [company_address, party_address]) {
            if (!address) continue;
            const result = await frappe.db.get_value("Address", address, "gst_category");
            if (IMPORT_GST_CATEGORIES.includes(result?.message?.gst_category)) return true;
        }

        return false;
    }

    async calculateDistribution() {
        const is_inter_state = await this.is_inter_state_distribution();
        for (const row of this.frm.doc.source_invoices || []) {
            const ratio = (row.distribution_ratio || 0) / 100;

            if (is_inter_state) {
                row.distributed_igst =
                    ((row.total_cgst || 0) + (row.total_sgst || 0) + (row.total_igst || 0)) * ratio;
                row.distributed_cgst = 0;
                row.distributed_sgst = 0;
            } else {
                row.distributed_igst = (row.total_igst || 0) * ratio;
                row.distributed_cgst = (row.total_cgst || 0) * ratio;
                row.distributed_sgst = (row.total_sgst || 0) * ratio;
            }

            row.distributed_cess = (row.total_cess || 0) * ratio;
            row.distributed_cess_non_advol = (row.total_cess_non_advol || 0) * ratio;
        }

        this.frm.refresh_field("source_invoices");
        this.calculateTaxesAndTotals();
    }

    calculateTaxesAndTotals() {
        const source_invoices = this.frm.doc.source_invoices || [];
        if (!source_invoices.length) return;

        const total_igst = source_invoices.reduce((s, r) => s + (r.distributed_igst || 0), 0);
        const total_cgst = source_invoices.reduce((s, r) => s + (r.distributed_cgst || 0), 0);
        const total_sgst = source_invoices.reduce((s, r) => s + (r.distributed_sgst || 0), 0);
        const total_cess = source_invoices.reduce((s, r) => s + (r.distributed_cess || 0), 0);
        const total_cess_non_advol = source_invoices.reduce(
            (s, r) => s + (r.distributed_cess_non_advol || 0),
            0,
        );

        const accounts = this.gst_accounts || {};
        const tax_type_map = {
            igst: [accounts.igst_account, total_igst],
            cgst: [accounts.cgst_account, total_cgst],
            sgst: [accounts.sgst_account, total_sgst],
            cess: [accounts.cess_account, total_cess],
            cess_non_advol: [accounts.cess_non_advol_account, total_cess_non_advol],
        };

        frappe.model.clear_table(this.frm.doc, "taxes");
        for (const [gst_tax_type, [account_head, tax_amount]] of Object.entries(tax_type_map)) {
            if (!account_head) continue;
            const row = frappe.model.add_child(this.frm.doc, "ISD Invoice Tax Item", "taxes");
            row.account_head = account_head;
            row.gst_tax_type = gst_tax_type;
            row.tax_amount = tax_amount;
        }

        this.frm.doc.total_eligible = source_invoices
            .filter((r) => !r.is_ineligible_for_itc)
            .reduce(
                (s, r) =>
                    s +
                    (r.distributed_igst || 0) +
                    (r.distributed_cgst || 0) +
                    (r.distributed_sgst || 0) +
                    (r.distributed_cess || 0),
                0,
            );
        this.frm.doc.total_ineligible = source_invoices
            .filter((r) => r.is_ineligible_for_itc)
            .reduce(
                (s, r) =>
                    s +
                    (r.distributed_igst || 0) +
                    (r.distributed_cgst || 0) +
                    (r.distributed_sgst || 0) +
                    (r.distributed_cess || 0),
                0,
            );

        this.frm.refresh_fields(["taxes", "total_eligible", "total_ineligible"]);
    }

    recalculate() {
        if (!(this.frm.doc.source_invoices || []).length) return;
        this.calculateDistribution();
        // this internally calculates taxes and totals 
    }
}
