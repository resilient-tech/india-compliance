frappe.ui.form.on("ISD Invoice", {
    onload(frm) {
        frm.isd_controller = new ISDInvoiceController(frm);
        frm.isd_controller.autofill_addresses();
    },

    refresh(frm) {
        frm.set_df_property("to_party_state", "options", [""].concat(frappe.boot.india_state_options));
        frm.isd_controller.update_address_labels();

        // Show button to create inter-company invoice on submit
        if (
            frm.doc.docstatus === 1 &&
            frm.doc.is_multi_company_setup &&
            !frm.doc.inter_company_invoice_reference
        ) {
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

        // Show link to mirror invoice if it exists
        if (frm.doc.inter_company_invoice_reference) {
            frm.add_custom_button(
                __("View Mirror Invoice"),
                () => {
                    frappe.set_route("Form", "ISD Invoice", frm.doc.inter_company_invoice_reference);
                },
                __("View"),
            );
        }
    },

    company(frm) {
        console.log("company changed", frm.doc.company);
        frm.set_value("is_multi_company_setup", 0)
    },

    is_multi_company_setup(frm) {
        if (!frm.doc.is_multi_company_setup) {
            frm.set_value("party_type", null);
            frm.set_value("party_name", null);
            frm.set_value("invoice_direction", null);
        } else {
            frm.set_value("invoice_direction", "Outward");
            frm.trigger("invoice_direction"); // above trigger does not work first time
        }
        // invoice_direction event handles update_address_labels + autofill_addresses
    },

    invoice_direction(frm) {
        console.log("invoice_direction changed", frm.doc.invoice_direction);
        frm.set_value("party_account", null);
        frm.isd_controller.update_address_labels();
        frm.isd_controller.autofill_addresses();
    },

    party_type(frm) {
        console.log("party_type changed", frm.doc.party_type);
        if (frm.doc.is_multi_company_setup) {
            frm.isd_controller.autofill_party_name();
        }
    },

    party_name(frm) {
        console.log("party_name changed", frm.doc.party_name);
        if (frm.doc.is_multi_company_setup && frm.doc.party_name) {
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
        frm.isd_controller.recalculate();
    },

    party_address(frm) {
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
            data_fields: [
                {
                    fieldtype: "Percent",
                    fieldname: "distribution_ratio",
                    label: __("Distribution Ratio(%)"),
                    default: 0.0,
                },
            ],
            get_query() {
                return {
                    filters: {
                        docstatus: 1,
                        company: this.dialog.get_value("company"),
                        billing_address: frm.doc.company_address,
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
                    frm.doc.distribution_ratio = data.distribution_ratio;
                }

                let distribution_ratio = 0.0;
                // pass the distribution ratio only when it is differnt form the exisiting one
                if (data.distribution_ratio && data.distribution_ratio != frm.doc.distribution_ratio) {
                    distribution_ratio = data.distribution_ratio;
                }

                frm.call("get_purchase_invoices", {
                    purchase_invoices: selections,
                    distribution_ratio: distribution_ratio,
                }).then(() => d.dialog.hide());
            },
        });
    },
});


frappe.ui.form.on("ISD Invoice Source Item", {
    purchase_invoice(frm, cdt, cdn) {
        if (!(frm.is_multi_company_setup && frm.doc.invoice_direction == "Inward")) {
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
                this.frm.doc.is_multi_company_setup &&
                this.frm.doc.invoice_direction === "Inward";
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
            if (!this.frm.doc.is_multi_company_setup) {
                console.log("Query for party_type - single company setup");
                return { filters: { name: ["in", ["Company"]] } };
            }
            console.log("Query for party_type - multi company setup");
            return { filters: { name: ["in", ["Supplier", "Customer"]] } };
        });

        this.frm.set_query("party_address", () => {

            // for single company setup
            if (!this.frm.doc.is_multi_company_setup) {
                return {
                    query: "frappe.contacts.doctype.address.address.address_query",
                    filters: {
                        link_doctype: "Company",
                        link_name: this.frm.doc.company,
                    },
                };
            }

            // for multi company setup
            if (!this.frm.doc.party_name || !this.frm.doc.party_type) {
                frappe.show_alert({
                    message: __("Please set Party Type and Party Name first"),
                    indicator: "orange",
                });
                return { filters: {} };
            }

            const filters = {
                link_doctype: this.frm.doc.party_type,
                link_name: this.frm.doc.party_name,
            };

            if (this.frm.doc.invoice_direction === "Inward") {
                filters.gst_category = "Input Service Distributor";
            }

            return {
                query: "frappe.contacts.doctype.address.address.address_query",
                filters,
            };

        });

        this.frm.set_query("account_head", "tax_items", () => {
            return {
                filters: {
                    company: this.frm.doc.company,
                    is_group: 0,
                },
            };
        });

        this.frm.set_query("purchase_invoice", "source_items", () => {
            return {
                query: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.search_purchase_invoice",
                params: {
                    company: this.frm.doc.company,
                    billing_address: this.frm.doc.company_address,
                },
            };
        });

        this.frm.set_query("party_account", () => {
            const account_type =
                this.frm.doc.invoice_direction === "Inward" ? "Receivable" : "Payable";
            return {
                filters: {
                    company: this.frm.doc.company,
                    account_type: account_type,
                    is_group: 0,
                },
            };
        });


    }

    async autofill_addresses() {
        /**
         * Shared entry point for is_multi_company_setup and invoice_direction changes.
         * Single company: autofills addresses directly.
         * Multi company: sets party_type → triggers cascade:
         *   party_type event → autofill_party_name → party_name event → autofill_addresses_for_party
         */
        if (!this.frm.doc.is_multi_company_setup) {
            await this.autofill_addresses_single_company();
            return;
        }

        const party_type = this.frm.doc.invoice_direction === "Outward" ? "Customer" : "Supplier";
        await this.frm.set_value("party_type", party_type);
        // Event chain handles the rest:
        //   party_type event → autofill_party_name → party_name event → autofill_addresses_for_party
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

    async autofill_addresses_single_company() {
        if (!this.frm.doc.company) return;

        const [company_address, party_address] = await Promise.all([
            this._get_address("Company", this.frm.doc.company, [["gst_category", "=", "Input Service Distributor"]]),
            this._get_address("Company", this.frm.doc.company, [["gst_category", "!=", "Input Service Distributor"]]),
        ]);

        this.frm.doc.company_address = company_address;
        this.frm.doc.party_address = party_address;
        this.frm.refresh_fields(["company_address", "party_address"]);
        await this.recalculate();
    }

    async autofill_party_name() {
        /** Set party_name to the first internal customer/supplier based on party_type. */
        if (!this.frm.doc.party_type) return;

        const is_customer = this.frm.doc.party_type === "Customer";
        const results = await frappe.db.get_list(this.frm.doc.party_type, {
            filters: { [is_customer ? "is_internal_customer" : "is_internal_supplier"]: 1 },
            fields: ["name"],
            limit: 1,
        });
        await this.frm.set_value("party_name", results[0]?.name || null);
    }

    async autofill_addresses_for_party() {
        if (!this.frm.doc.company || !this.frm.doc.party_name || !this.frm.doc.party_type) return;

        const is_outward = this.frm.doc.invoice_direction === "Outward";

        const [company_address, party_address] = await Promise.all([
            this._get_address("Company", this.frm.doc.company, [["gst_category", is_outward ? "=" : "!=", "Input Service Distributor"]]),
            this._get_address(
                this.frm.doc.party_type,
                this.frm.doc.party_name,
                !is_outward ? [["gst_category", "=", "Input Service Distributor"]] : []
            ),
        ]);

        this.frm.doc.company_address = company_address;
        this.frm.doc.party_address = party_address;
        this.frm.refresh_fields(["company_address", "party_address"]);
        await this.recalculate();
    }

    update_address_labels() {
        const LABELS = {
            default: { company_address: __("Company Address"),              party_address: __("Party Address") },
            Outward: { company_address: __("Company Address (Distributor)"), party_address: __("Party Address (Recipient)") },
            Inward:  { company_address: __("Company Address (Recipient)"),   party_address: __("Party Address (Distributor)") },
        };

        const key = !this.frm.doc.is_multi_company_setup ? "default" : (this.frm.doc.invoice_direction || "Inward");
        const labels = LABELS[key] || LABELS.Inward;

        this.frm.set_df_property("company_address", "label", labels.company_address);
        this.frm.set_df_property("party_address", "label", labels.party_address);

        if (this.frm.doc.is_multi_company_setup) {
            this.frm.refresh_field("company_address");
            this.frm.refresh_field("party_address");
        }
    }

    async autofill_source_item(cdt, cdn) {
        /**
         * Fetch tax totals from Purchase Invoice Items for a given row,
         */

        const row = locals[cdt][cdn];
        if (!row.purchase_invoice) return;

        const result = await this.frm.call("get_source_items_from_purchase_invoices", {
            purchase_invoices: [row.purchase_invoice],
        });
        const items = result.message || [];
        const match = items.find(item => item.is_ineligible_for_itc == row.is_ineligible_for_itc);
        if (!match) return;

        await frappe.model.set_value(cdt, cdn, {
            total_igst: match.total_igst || 0,
            total_cgst: match.total_cgst || 0,
            total_sgst: match.total_sgst || 0,
            total_cess: match.total_cess || 0,
            total_cess_non_advol: match.total_cess_non_advol || 0,
        });
        this.recalculate();
    }

    async recalculate() {
        if (!(this.frm.doc.source_items || []).length) return;

        await this.frm.call("calculate_distribution");
        await this.frm.call("calculate_taxes_and_totals");
        await frappe.show_alert({ message: __("Taxes recalculated"), indicator: "info" });
    }

}
