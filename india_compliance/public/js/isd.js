// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

india_compliance.ISD_GST_CATEGORY = "Input Service Distributor";
india_compliance.GST_TAX_TYPES = ["cgst", "sgst", "igst", "cess", "cess_non_advol"];
india_compliance.IMPORT_GST_CATEGORIES = ["Overseas", "SEZ"];

india_compliance.get_address_query = function (link_doctype, link_name, extra_filters = []) {
    return {
        filters: [
            ["Dynamic Link", "link_doctype", "=", link_doctype],
            ["Dynamic Link", "link_name", "=", link_name],
            ...extra_filters,
        ],
    };
};

// Shared client controller for the two ISD doctypes.
india_compliance.ISDController = class ISDController {
    constructor(frm) {
        this.frm = frm;
        this.setup();
    }

    get is_distribution_side() {
        return this.frm.doctype === "ISD Distribution Invoice";
    }

    get distribute_expense() {
        return cint(gst_settings.distribute_expense_with_isd_credit);
    }

    toggle_expense_fields() {
        const hidden = this.distribute_expense ? 0 : 1;
        this.frm.toggle_display("total_expense", !hidden);

        const grid = this.frm.fields_dict.source_items?.grid;
        if (grid) {
            grid.update_docfield_property("total_expense", "hidden", hidden);
            grid.update_docfield_property("distributed_expense", "hidden", hidden);
            this.frm.refresh_field("source_items");
        }
    }

    setup() {
        this.set_queries();
        this.load_company_defaults();
    }

    async load_company_defaults() {
        await this.fetch_gst_accounts();
        await this.fetch_default_cost_center();
        if (this.frm.is_new()) this.set_available_taxes();
    }

    set_available_taxes() {
        // seed the taxes table with every configured input GST head with amount 0 to give familiar UI
        const accounts = this.gst_accounts || {};
        const existing = Object.fromEntries((this.frm.doc.taxes || []).map((tax) => [tax.gst_tax_type, tax]));

        for (const t of india_compliance.GST_TAX_TYPES) {
            const account_head = accounts[`${t}_account`];
            if (!account_head) continue;

            let row = existing[t];
            if (!row) {
                row = frappe.model.add_child(this.frm.doc, "ISD Tax Item", "taxes");
                row.gst_tax_type = t;
                row.tax_amount = 0;
            }
            row.account_head = account_head;
        }

        this.frm.refresh_field("taxes");
    }

    set_provisional_labels() {
        const against_party = this.frm.doc.is_against_party;
        this.frm.set_df_property(
            "isd_provisional_account",
            "label",
            against_party ? "Party Account" : "ISD Provisional Account",
        );
        this.frm.set_df_property(
            "isd_provisional_amount",
            "label",
            against_party ? "Party Amount" : "ISD Provisional Amount",
        );
    }

    // ------------------------------------------------------------------ link field queries
    set_queries() {
        const frm = this.frm;

        frm.set_query("distribution_address", () => this._address_query("distribution_address"));
        frm.set_query("recipient_address", () => this._address_query("recipient_address"));

        frm.set_query("party_type", () => {
            return { filters: { name: ["in", ["Customer", "Supplier"]] } };
        });

        frm.set_query("party", () => {
            const internal_field =
                frm.doc.party_type == "Customer" ? "is_internal_customer" : "is_internal_supplier";
            return { filters: { [internal_field]: 1 } };
        });

        frm.set_query("account_head", "taxes", () => {
            return { filters: { name: ["in", Object.values(this.gst_accounts || {}).filter(Boolean)] } };
        });

        const company_accounts = () => ({ filters: { company: frm.doc.company, is_group: 0 } });
        frm.set_query("isd_provisional_account", company_accounts);
        frm.set_query("cost_center", company_accounts);
        frm.set_query("expense_head", "source_items", company_accounts);
        frm.set_query("cost_center", "source_items", company_accounts);

        if (this.is_distribution_side) {
            frm.set_query("purchase_invoice", () => ({
                filters: {
                    docstatus: 1,
                    is_isd_applicable: 1,
                    company: frm.doc.company,
                    company_gstin: frm.doc.distribution_gstin,
                },
            }));
            frm.set_query("credit_note_against", () => ({
                filters: { docstatus: 1, company: frm.doc.company, is_credit_note: 0 },
            }));
        } else {
            frm.set_query("isd_distribution_invoice_reference", () => ({
                filters: {
                    docstatus: 1,
                    distribution_gstin: frm.doc.distribution_gstin,
                    recipient_gstin: frm.doc.recipient_gstin,
                },
            }));
            frm.set_query("credit_note_against", () => ({ filters: { docstatus: 1 } }));
        }
    }

    _address_query(field) {
        const frm = this.frm;
        // distribution_address is always the ISD registration; recipient_address is always non-ISD
        const category_op = field === "distribution_address" ? "=" : "!=";
        const extra = [["gst_category", category_op, india_compliance.ISD_GST_CATEGORY]];

        if (!frm.doc.company) {
            frappe.show_alert({ message: __("Please set Company first"), indicator: "orange" });
            return { filters: {} };
        }

        // invoice owner address is linked by frm.doc.company
        const invoice_owner_address = this.is_distribution_side
            ? "distribution_address"
            : "recipient_address";

        if (!frm.doc.is_against_party || invoice_owner_address == field) {
            return india_compliance.get_address_query("Company", frm.doc.company, extra);
        }

        if (!frm.doc.party_type || !frm.doc.party) {
            frappe.show_alert({
                message: __("Please set Party Type and Party first"),
                indicator: "orange",
            });
            return { filters: {} };
        }
        return india_compliance.get_address_query(frm.doc.party_type, frm.doc.party, extra);
    }

    // ------------------------------------------------------------------ autofill (single backend call)
    async fetch_autofill(changed_field) {
        const frm = this.frm;
        if (frm.__updating_isd_autofill || !frm.doc.company) return;

        const { message } = await frappe.call({
            method: "india_compliance.gst_india.utils.isd.get_isd_autofill_values",
            args: {
                doctype: frm.doctype,
                changed_field,
                doc: {
                    company: frm.doc.company,
                    is_against_party: frm.doc.is_against_party || 0,
                    party_type: frm.doc.party_type || null,
                    party: frm.doc.party || null,
                    recipient_address: frm.doc.recipient_address || null,
                    posting_date: frm.doc.posting_date || null,
                    branch_turnover: frm.doc.branch_turnover || null,
                },
            },
        });

        if (!message) return;

        frm.__updating_isd_autofill = true;
        await frm.set_value(message); //TODO: instead of this we can do Object.assign and then call refresh
        await frm.isd_controller.set_queries();
        frm.__updating_isd_autofill = false;
    }

    // ------------------------------------------------------------------ address display / pos
    set_address_display(address_field, display_field) {
        const address = this.frm.doc[address_field];
        if (!address) {
            this.frm.set_value(display_field, "");
            return;
        }
        frappe
            .call({
                method: "frappe.contacts.doctype.address.address.get_address_display",
                args: { address_dict: address },
            })
            .then((r) => this.frm.set_value(display_field, r.message || ""));
    }

    async set_pos(address_field, pos_field) {
        const address = this.frm.doc[address_field];
        if (!address) {
            this.frm.set_value(pos_field, "");
            return;
        }
        const { message } = await frappe.db.get_value("Address", address, ["gst_state_number", "gst_state"]);
        if (message) this.frm.set_value(pos_field, `${message.gst_state_number}-${message.gst_state}`);
    }

    // ------------------------------------------------------------------ distribution preview
    async is_inter_state_distribution() {
        const frm = this.frm;

        // SEZ / overseas recipient is always inter-state (IGST), regardless of place of supply
        if (frm.doc.recipient_address) {
            const { message } = await frappe.db.get_value(
                "Address",
                frm.doc.recipient_address,
                "gst_category",
            );
            if (india_compliance.IMPORT_GST_CATEGORIES.includes(message?.gst_category)) return true;
        }

        if (frm.doc.distribution_pos && frm.doc.recipient_pos)
            return frm.doc.distribution_pos !== frm.doc.recipient_pos;

        return false;
    }

    get signed_ratio() {
        // signed turnover ratio; credit notes reverse credit, so they carry a negative sign
        const sign = this.frm.doc.is_credit_note ? -1 : 1;
        const { branch_turnover, total_turnover } = this.frm.doc;
        return total_turnover ? (sign * flt(branch_turnover)) / flt(total_turnover) : 0;
    }

    _calculate_distribution_row(row, inter_state) {
        const ratio = this.signed_ratio;
        const _p = precision("distributed_igst", row);
        const _pe = precision("distributed_expense", row);

        if (inter_state) {
            // inter-state -> everything collapses to IGST (Rule 39(1)(e), (g))
            row.distributed_igst = flt(
                ((row.total_igst || 0) + (row.total_cgst || 0) + (row.total_sgst || 0)) * ratio,
                _p,
            );
            row.distributed_cgst = 0;
            row.distributed_sgst = 0;
        } else {
            // intra-state -> each credit keeps its type (Rule 39(1)(e), (f))
            row.distributed_igst = flt((row.total_igst || 0) * ratio, _p);
            row.distributed_cgst = flt((row.total_cgst || 0) * ratio, _p);
            row.distributed_sgst = flt((row.total_sgst || 0) * ratio, _p);
        }

        row.distributed_cess = flt((row.total_cess || 0) * ratio, _p);
        row.distributed_cess_non_advol = flt((row.total_cess_non_advol || 0) * ratio, _p);
        row.distributed_expense = this.distribute_expense ? flt((row.total_expense || 0) * ratio, _pe) : 0;
    }

    async recalculate() {
        if (!(this.frm.doc.source_items || []).length) return;

        const inter_state = await this.is_inter_state_distribution();
        for (const row of this.frm.doc.source_items) {
            this._calculate_distribution_row(row, inter_state);
        }

        this.frm.refresh_field("source_items");
        this.calculate_taxes_and_totals();
    }

    calculate_taxes_and_totals() {
        const rows = this.frm.doc.source_items || [];
        const distribution_side = this.is_distribution_side;
        const ratio = this.signed_ratio;

        const totals = Object.fromEntries(india_compliance.GST_TAX_TYPES.map((t) => [t, 0]));
        let total_eligible = 0,
            total_ineligible = 0,
            total_expense = 0;

        for (const r of rows) {
            const _p = precision("distributed_igst", r);
            let row_total = 0;
            for (const t of india_compliance.GST_TAX_TYPES) {
                row_total += r[`distributed_${t}`] || 0;

                totals[t] += distribution_side
                    ? flt((r[`total_${t}`] || 0) * ratio, _p)
                    : r[`distributed_${t}`] || 0;
            }
            if (r.is_ineligible_for_itc) total_ineligible += row_total;
            else total_eligible += row_total;
            total_expense += r.distributed_expense || 0;
        }

        this.set_tax_amounts(totals);

        // mirror server-side set_provisional_values: the provisional / party account receives the
        // distributed taxes plus the distributed expense
        const isd_provisional_amount =
            (this.frm.doc.taxes || []).reduce((sum, tax) => sum + flt(tax.tax_amount), 0) + total_expense;

        this.frm.doc.total_eligible = flt(total_eligible, precision("total_eligible"));
        this.frm.doc.total_ineligible = flt(total_ineligible, precision("total_ineligible"));
        this.frm.doc.total_expense = flt(total_expense, precision("total_expense"));
        this.frm.doc.isd_provisional_amount = flt(
            isd_provisional_amount,
            precision("isd_provisional_amount"),
        );

        this.frm.refresh_fields([
            "taxes",
            "total_eligible",
            "total_ineligible",
            "total_expense",
            "isd_provisional_amount",
        ]);
    }

    set_tax_amounts(totals) {
        const accounts = this.gst_accounts || {};
        const existing = Object.fromEntries((this.frm.doc.taxes || []).map((tax) => [tax.gst_tax_type, tax]));

        for (const t of india_compliance.GST_TAX_TYPES) {
            let row = existing[t];
            if (!row) {
                const account_head = accounts[`${t}_account`];
                if (!account_head || !totals[t]) continue; //if both account head and total are missing, skip

                row = frappe.model.add_child(this.frm.doc, "ISD Tax Item", "taxes"); //add row if not existing
                row.account_head = account_head;
                row.gst_tax_type = t;
            }
            row.tax_amount = flt(totals[t], precision("tax_amount", row));
        }
    }

    // ------------------------------------------------------------------ company defaults
    async fetch_gst_accounts() {
        if (!this.frm.doc.company) return;
        const { message } = await frappe.call({
            method: "india_compliance.gst_india.utils.isd.get_input_gst_accounts",
            args: { company: this.frm.doc.company },
        });
        this.gst_accounts = message || {};
    }

    async fetch_default_cost_center() {
        if (!this.frm.doc.company) return;
        const { message } = await frappe.db.get_value("Company", this.frm.doc.company, "cost_center");
        this.default_cost_center = message?.cost_center || null;
    }

    set_common_buttons() {
        if (this.frm.doc.docstatus === 1) {
            this.frm.add_custom_button(
                __("Accounting Ledger"),
                () => {
                    frappe.route_options = {
                        voucher_no: this.frm.doc.name,
                        from_date: this.frm.doc.posting_date,
                        to_date: this.frm.doc.posting_date,
                        company: this.frm.doc.company,
                        group_by: "Group by Voucher (Consolidated)",
                        show_cancelled_entries: this.frm.doc.docstatus === 2,
                    };
                    frappe.set_route("query-report", "General Ledger");
                },
                __("View"),
            );
        }
    }
};
