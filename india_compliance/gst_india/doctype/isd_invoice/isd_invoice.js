const IMPORT_GST_CATEGORIES = ["Overseas", "SEZ"];

frappe.ui.form.on("ISD Invoice", {
    setup(frm) {
        frm.isd_controller = new ISDInvoiceController(frm);
    },

    refresh(frm) {
        frm.isd_controller.update_address_labels(); // Show button to create inter-company invoice on submit
        if (frm.doc.docstatus === 1 && frm.doc.is_against_party) {
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
        frm.doc.is_against_party = 0;
        frm.refresh_field("is_against_party");
        frm.isd_controller.fetch_gst_accounts();
        fetch_isd_autofill(frm, "company");
    },

    is_against_party(frm) {
        if (frm.__updating_isd_autofill) return;
        fetch_isd_autofill(frm, "is_against_party");
    },

    credit_flow(frm) {
        frm.isd_controller.update_address_labels();
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party) return;
        fetch_isd_autofill(frm, "credit_flow");
    },

    party_type(frm) {
        if (frm.doc.is_against_party) frm.isd_controller.update_party_label();
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party) return;
        fetch_isd_autofill(frm, "party_type");
    },

    party(frm) {
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party || !frm.doc.party) return;
        fetch_isd_autofill(frm, "party");
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
        // rearrangement runs after make is complete; patch handles non-cached case
        const _make = d.make.bind(d);
        const rearrange = () => {
            const $dist = d.dialog?.fields_dict?.distribution_ratio?.$wrapper?.closest(".form-section");
            const $results = d.dialog?.fields_dict?.results_area?.$wrapper?.closest(".form-section");
            if ($dist?.length && $results?.length) $dist.insertBefore($results);
        };

        d.make = () => { _make(); rearrange(); };
        if (d.dialog) rearrange();
    },
});

frappe.ui.form.on("ISD Invoice Source Item", {
    source_invoices_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "distribution_ratio", frm.doc.distribution_ratio || 0);
    },
    purchase_invoice(frm, cdt, cdn) {
        if (!(frm.is_against_party && frm.doc.credit_flow == "Credit Receipt")) {
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

async function fetch_isd_autofill(frm, changed_field) {
    if (frm.__updating_isd_autofill || !frm.doc.company) return;

    const r = await frappe.call({
        method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_isd_autofill_values",
        args: {
            changed_field,
            company: frm.doc.company,
            is_against_party: frm.doc.is_against_party || 0,
            credit_flow: frm.doc.credit_flow || null,
            party_type: frm.doc.party_type || null,
            party: frm.doc.party || null,
        },
    });

    if (!r?.message) return;

    frm.__updating_isd_autofill = true;
    await frm.set_value(r.message);
    frm.__updating_isd_autofill = false;
}

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
                this.frm.doc.is_against_party && this.frm.doc.credit_flow === "Credit Receipt";
            const filters = {
                link_doctype: "Company",
                link_name: this.frm.doc.company,
            };
            // gst_category should be ISD if company is distributor
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

            const is_company_recipient =
            this.frm.doc.is_against_party && this.frm.doc.credit_flow === "Credit Receipt";
            const filters = {
                link_doctype: this.frm.doc.party_type,
                link_name: this.frm.doc.party,
            };

            if (is_company_recipient) {
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
            const account_type = this.frm.doc.credit_flow === "Credit Receipt" ? "Receivable" : "Payable";
            return {
                filters: {
                    company: this.frm.doc.company,
                    account_type: account_type,
                    is_group: 0,
                },
            };
        });
    }

    update_party_label() {
        const party_type = this.frm.doc.party_type;
        this.frm.set_df_property("party", "label", party_type);
        this.frm.refresh_field("party");
    }

    update_address_labels() {
        const LABELS = {
            "default": {
                company_address: __("Select Company Address"),
                party_address: __("Select Party Address"),
            },
            "Credit Distribution": {
                company_address: __("Select Company Address (Distributor)"),
                party_address: __("Select Party Address (Recipient)"),
            },
            "Credit Receipt": {
                company_address: __("Select Company Address (Recipient)"),
                party_address: __("Select Party Address (Distributor)"),
            },
        };

        const key = !this.frm.doc.is_against_party ? "default" : this.frm.doc.credit_flow;
        const labels = LABELS[key] || LABELS["default"];

        this.frm.set_df_property("company_address", "label", labels.company_address);
        this.frm.set_df_property("party_address", "label", labels.party_address);
        this.frm.refresh_field("company_address");
        this.frm.refresh_field("party_address");
    }

    autofill_source_item(cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.purchase_invoice) return;

        frappe.call({
            method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_source_invoices_from_purchase_invoices",
            args: { purchase_invoices: [row.purchase_invoice] },
            callback: (result) => {
                const items = result.message || [];
                const match = items.find((item) => item.is_ineligible_for_itc == row.is_ineligible_for_itc);
                if (!match) {
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
            },
        });
    }
    // can optimize this using the fetch_isd_autofill
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
    fetch_gst_accounts() {
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

    async calculate_distribution() {
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
        this.calculate_taxes_and_totals();
    }

    calculate_taxes_and_totals() {
        const source_invoices = this.frm.doc.source_invoices || [];
        if (!source_invoices.length) return;

        let total_igst = 0,
            total_cgst = 0,
            total_sgst = 0,
            total_cess = 0,
            total_cess_non_advol = 0;
        let total_eligible = 0,
            total_ineligible = 0;
        for (const r of source_invoices) {
            total_igst += r.distributed_igst;
            total_cgst += r.distributed_cgst;
            total_sgst += r.distributed_sgst;
            total_cess += r.distributed_cess;
            total_cess_non_advol += r.distributed_cess_non_advol;
            const row_total =
                (r.distributed_igst) +
                (r.distributed_cgst) +
                (r.distributed_sgst) +
                (r.distributed_cess);
            if (r.is_ineligible_for_itc) total_ineligible += row_total;
            else total_eligible += row_total;
        }

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

        this.frm.doc.total_eligible = total_eligible;
        this.frm.doc.total_ineligible = total_ineligible;

        this.frm.refresh_fields(["taxes", "total_eligible", "total_ineligible"]);
    }

    recalculate() {
        if (!(this.frm.doc.source_invoices || []).length) return;
        this.calculate_distribution();
    }
}
