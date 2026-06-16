frappe.ui.form.on("ISD Invoice", {
    setup(frm) {
        frm.isd_controller = new ISDInvoiceController(frm);
    },

    onload(frm) {
        if (frm.is_new() && !frm.doc.company) {
            frm.set_value("company", frappe.defaults.get_user_default("Company"));
        }
    },

    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.is_against_party && frappe.model.can_create("ISD Invoice")) {
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
        if (frm.doc.docstatus === 1 && !frm.doc.is_credit_note && frappe.model.can_create("ISD Invoice")) {
            frm.add_custom_button(
                __("Credit Note"),
                () => {
                    frappe.model.open_mapped_doc({
                        method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.make_credit_note",
                        frm: frm,
                    });
                },
                __("Create"),
            );
        }
        if (frm.doc.docstatus === 1) {
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
                __("View"),
            );
        }
    },

    async company(frm) {
        frm.isd_controller.fetch_gst_accounts();
        await fetch_isd_autofill(frm, "company");
    },

    async is_against_party(frm) {
        if (frm.__updating_isd_autofill) return;
        await fetch_isd_autofill(frm, "is_against_party");
        frm.isd_controller.update_address_labels();
    },

    async credit_flow(frm) {
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party) return;
        await fetch_isd_autofill(frm, "credit_flow");
        frm.isd_controller.update_address_labels();
    },

    async party_type(frm) {
        if (frm.doc.is_against_party) frm.isd_controller.update_party_label();
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party) return;
        await fetch_isd_autofill(frm, "party_type");
    },

    async party(frm) {
        if (frm.__updating_isd_autofill || !frm.doc.is_against_party || !frm.doc.party) return;
        await fetch_isd_autofill(frm, "party");
    },

    is_external_invoice(frm) {
        if (frm.doc.is_external_invoice) {
            frm.clear_table("source_invoices");
            frm.refresh_field("source_invoices");
        }
    },

    async default_distribution_ratio(frm) {
        if (frm.doc.default_distribution_ratio < 0 || frm.doc.default_distribution_ratio > 100) {
            frappe.show_alert({
                message: __("Distribution ratio must be between 0 and 100"),
                indicator: "red",
            });
            return;
        }

        await frm.isd_controller.recalculate();
    },

    async company_address(frm) {
        frm.isd_controller.set_address_display("company_address", "company_address_display");
        await frm.isd_controller.recalculate();
    },

    async party_address(frm) {
        frm.isd_controller.set_address_display("party_address", "party_address_display");
        await frm.isd_controller.recalculate();
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
                    default: frm.doc.default_distribution_ratio || 0.0,
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

                frm.call("get_purchase_invoices", {
                    purchase_invoices: selections,
                    distribution_ratio: data.distribution_ratio || 0.0,
                }).then(() => {
                    d.dialog.hide();
                    frm.set_value("default_distribution_ratio", data.distribution_ratio || 0.0);
                });
            },
        });

        // Move distribution_ratio section before the results area.
        // rearrangement runs after make is complete; this is required for non-cached loads
        const _make = d.make.bind(d);
        const rearrange = () => {
            const $dist = d.dialog?.fields_dict?.distribution_ratio?.$wrapper?.closest(".form-section");
            const $results = d.dialog?.fields_dict?.results_area?.$wrapper?.closest(".form-section");
            if ($dist?.length && $results?.length) $dist.insertBefore($results);
        };

        d.make = () => {
            _make();
            rearrange();
        };
        if (d.dialog) rearrange();
    },
});

const CREDIT_FLOW = {
    DISTRIBUTION: "Credit Distribution",
    RECEIPT: "Credit Receipt",
};

frappe.ui.form.on("ISD Invoice Source Item", {
    async source_invoices_add(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "distribution_ratio", frm.doc.default_distribution_ratio || 0);
        await frm.isd_controller.recalculate();
    },

    async source_invoices_remove(frm) {
        await frm.isd_controller.recalculate();
    },
    purchase_invoice(frm, cdt, cdn) {
        if (!(frm.is_against_party && frm.doc.credit_flow == CREDIT_FLOW.RECEIPT)) {
            frm.isd_controller.autofill_source_item(cdt, cdn);
        }
    },
    async is_ineligible_for_itc(frm, cdt, cdn) {
        frm.isd_controller.autofill_source_item(cdt, cdn);
        await frm.isd_controller.recalculate();
    },

    async distribution_ratio(frm) {
        await frm.isd_controller.recalculate();
    },
});

async function fetch_isd_autofill(frm, changed_field) {
    if (frm.__updating_isd_autofill || !frm.doc.company) return;

    const r = await frappe.call({
        method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_isd_autofill_values",
        args: {
            changed_field,
            doc: {
                company: frm.doc.company,
                is_against_party: frm.doc.is_against_party || 0,
                credit_flow: frm.doc.credit_flow || null,
                party_type: frm.doc.party_type || null,
                party: frm.doc.party || null,
            },
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
        this.fetch_gst_accounts();
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
                this.frm.doc.is_against_party && this.frm.doc.credit_flow === CREDIT_FLOW.RECEIPT;
            const extra = is_company_recipient ? {} : { gst_category: "Input Service Distributor" };
            return india_compliance.get_address_query("Company", this.frm.doc.company, extra);
        });

        this.frm.set_query("party_type", () => {
            if (!this.frm.doc.is_against_party) {
                return { filters: { name: ["in", ["Company"]] } };
            }
            return { filters: { name: ["in", ["Supplier", "Customer"]] } };
        });

        this.frm.set_query("party", () => {
            const party_type = this.frm.doc.party_type;
            if (!party_type || !["Supplier", "Customer"].includes(party_type)) return;
            const internal_field =
                party_type === "Customer" ? "is_internal_customer" : "is_internal_supplier";
            return { filters: { [internal_field]: 1 } };
        });

        this.frm.set_query("party_address", () => {
            // for single company setup
            if (!this.frm.doc.is_against_party) {
                return india_compliance.get_address_query("Company", this.frm.doc.company);
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
                this.frm.doc.is_against_party && this.frm.doc.credit_flow === CREDIT_FLOW.RECEIPT;
            const extra = is_company_recipient ? { gst_category: "Input Service Distributor" } : {};
            return india_compliance.get_address_query(this.frm.doc.party_type, this.frm.doc.party, extra);
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
            const account_type = this.frm.doc.party_type === "Customer" ? "Receivable" : "Payable";
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
            default: {
                company_address: __("Company Address"),
                party_address: __("Party Address"),
            },
            [CREDIT_FLOW.DISTRIBUTION]: {
                company_address: __("Company Address (Distributor)"),
                party_address: __("Party Address (Recipient)"),
            },
            [CREDIT_FLOW.RECEIPT]: {
                company_address: __("Company Address (Recipient)"),
                party_address: __("Party Address (Distributor)"),
            },
        };

        const key = !this.frm.doc.is_against_party ? "default" : this.frm.doc.credit_flow;
        const labels = LABELS[key] || LABELS["default"];

        this.frm.set_df_property("company_address", "label", labels.company_address);
        this.frm.set_df_property("party_address", "label", labels.party_address);
        this.frm.refresh_fields(["company_address", "party_address"]);
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
                    frappe.model.set_value(
                        cdt,
                        cdn,
                        india_compliance.GST_TAX_TYPES.map((t) => `total_${t}`).reduce(
                            (acc, key) => ({ ...acc, [key]: 0 }),
                            {},
                        ),
                    );
                    return;
                }

                frappe.model.set_value(
                    cdt,
                    cdn,
                    india_compliance.GST_TAX_TYPES.map((t) => `total_${t}`).reduce(
                        (acc, key) => ({ ...acc, [key]: match[key] || 0 }),
                        {},
                    ),
                );
                this.recalculate();
            },
        });
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
            if (india_compliance.IMPORT_GST_CATEGORIES.includes(result?.message?.gst_category)) return true;
        }

        return false;
    }

    async calculate_distribution() {
        const is_inter_state = await this.is_inter_state_distribution();
        // credit notes store distributed amounts as negative (reverse of the original)
        const sign = this.frm.doc.is_credit_note ? -1 : 1;
        for (const row of this.frm.doc.source_invoices || []) {
            const ratio = (sign * (row.distribution_ratio || 0)) / 100;

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

        const totals = Object.fromEntries(india_compliance.GST_TAX_TYPES.map((t) => [t, 0]));
        let total_eligible = 0,
            total_ineligible = 0;

        for (const r of source_invoices) {
            for (const t of india_compliance.GST_TAX_TYPES) {
                totals[t] += r[`distributed_${t}`] || 0;
            }
            const row_total = india_compliance.GST_TAX_TYPES.reduce(
                (sum, t) => sum + (r[`distributed_${t}`] || 0),
                0,
            );
            if (r.is_ineligible_for_itc) total_ineligible += row_total;
            else total_eligible += row_total;
        }

        const accounts = this.gst_accounts || {};
        const existing_taxes = Object.fromEntries(
            (this.frm.doc.taxes || []).map((tax) => [tax.gst_tax_type, tax]),
        );

        for (const gst_tax_type of india_compliance.GST_TAX_TYPES) {
            const account_head = accounts[`${gst_tax_type}_account`];
            if (!account_head) continue;

            const row =
                existing_taxes[gst_tax_type] ||
                frappe.model.add_child(this.frm.doc, "ISD Invoice Tax Item", "taxes");
            row.account_head = account_head;
            row.gst_tax_type = gst_tax_type;
            row.tax_amount = totals[gst_tax_type];
        }

        this.frm.doc.taxes = (this.frm.doc.taxes || []).filter((tax) => tax.tax_amount);
        this.frm.doc.total_eligible = total_eligible;
        this.frm.doc.total_ineligible = total_ineligible;

        this.frm.refresh_fields(["taxes", "total_eligible", "total_ineligible"]);
    }

    async recalculate() {
        if (!(this.frm.doc.source_invoices || []).length) return;
        await this.calculate_distribution();
    }
}
