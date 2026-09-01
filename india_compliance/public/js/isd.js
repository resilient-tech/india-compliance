// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

india_compliance.get_address_query = function (link_doctype, link_name, extra_filters = []) {
    return {
        filters: [
            ["Dynamic Link", "link_doctype", "=", link_doctype],
            ["Dynamic Link", "link_name", "=", link_name],
            ...extra_filters,
        ],
    };
};

india_compliance.show_isd_invoice_distribution_dialog = function (purchase_invoice) {
    const company = purchase_invoice.company;

    const dialog = new frappe.ui.Dialog({
        title: __("Distribute ITC to Recipient Branches"),
        size: "extra-large",
        fields: [
            { fieldtype: "HTML", fieldname: "purchase_invoice_summary" },
            { fieldtype: "Section Break" },
            {
                fieldtype: "Date",
                fieldname: "posting_date",
                label: __("Posting Date"),
                default: frappe.datetime.get_today(),
                reqd: 1,
                change() {
                    fetch_and_prefill_grid();
                },
            },
            {
                fieldtype: "Check",
                fieldname: "is_against_party",
                label: __("Against Party"),
                default: 0,
                change() {
                    const hidden = !this.get_value();
                    for (const field of ["party_type", "party"])
                        distribution_grid.update_docfield_property(field, "hidden", hidden);
                    distribution_grid.reset_grid();
                },
            },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Currency",
                fieldname: "total_turnover",
                label: __("Total Turnover"),
                default: 0,
                reqd: 1,
                options: "Company:company:default_currency",
                change() {
                    calculate_distribution_ratios();
                },
            },

            { fieldtype: "Section Break" },
            {
                label: __("Distribution Table"),
                fieldtype: "Table",
                fieldname: "distribution_table",
                in_place_edit: true,
                fields: [
                    {
                        fieldtype: "Select",
                        options: ["Company", "Customer", "Supplier"],
                        fieldname: "party_type",
                        label: __("Party Type"),
                        default: "Company",
                        in_list_view: 1,
                        columns: 1,
                        hidden: 1,
                    },
                    {
                        fieldtype: "Dynamic Link",
                        fieldname: "party",
                        label: __("Party"),
                        default: company,
                        in_list_view: 1,
                        columns: 2,
                        hidden: 1,
                        get_options: (df) => df.doc.party_type,
                        get_query(doc) {
                            if (doc.party_type === "Company") return {};
                            const field =
                                doc.party_type === "Customer"
                                    ? "is_internal_customer"
                                    : "is_internal_supplier";
                            return { filters: { [field]: 1 } };
                        },
                    },
                    {
                        fieldtype: "Link",
                        options: "Address",
                        fieldname: "address",
                        label: __("Address"),
                        in_list_view: 1,
                        reqd: 1,
                        columns: 2,
                        get_query(doc) {
                            return india_compliance.get_address_query(doc.party_type, doc.party);
                        },
                        change() {
                            const { address, party_type, party } = this.doc;
                            if (!address) return;
                            const { posting_date } = dialog.get_values();

                            frappe.call({
                                method: "india_compliance.gst_india.utils.isd.get_distribution_addresses",
                                args: {
                                    party_type,
                                    party,
                                    company,
                                    pi_posting_date: posting_date,
                                    address,
                                },
                                callback: ({ message: { addresses: [row] = [] } = {} }) => {
                                    if (!row || this.doc.address !== address) return;
                                    const { gstin, gst_category, gst_state, turnover_amount } = row;
                                    Object.assign(this.doc, {
                                        gstin,
                                        gst_category,
                                        gst_state,
                                        turnover_amount,
                                    });
                                    fill_total_turnover();
                                    calculate_distribution_ratios();
                                    distribution_grid.refresh_row(this.doc.idx);
                                },
                            });
                        },
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "gstin",
                        label: __("GSTIN"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 1,
                    },
                    { fieldtype: "Data", fieldname: "gst_category", label: __("GST Category") },
                    {
                        fieldtype: "Data",
                        fieldname: "gst_state",
                        label: __("GST State"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 1,
                    },
                    {
                        fieldtype: "Currency",
                        fieldname: "turnover_amount",
                        label: __("Turnover Amount (Prev. Yr.)"),
                        in_list_view: 1,
                        default: 0,
                        columns: 2,
                        options: "Company:company:default_currency",
                        change() {
                            fill_total_turnover();
                            calculate_distribution_ratios();
                        },
                    },
                    {
                        fieldtype: "Float",
                        fieldname: "distribution_ratio",
                        label: __("Distribution Ratio (%)"),
                        in_list_view: 1,
                        read_only: 1,
                        default: 0,
                        columns: 1,
                    },
                ],
            },
        ],
        primary_action_label: __("Create ISD Distribution Invoices"),
        primary_action() {
            const values = dialog.get_values();
            if (!values) return;
            const { distribution_table = [], is_against_party, posting_date, total_turnover } = values;
            const rows = distribution_table.filter((row) => row.turnover_amount);
            if (!rows.length) {
                frappe.msgprint(__("Enter turnover for at least one branch."));
                return;
            }

            if (rows.some((row) => parseFloat(row.turnover_amount) < 0)) {
                frappe.msgprint(__("Turnover cannot be negative."));
                return;
            }

            dialog.hide();

            const payload = rows.map((row) => ({
                turnover_amount: parseFloat(row.turnover_amount) || 0,
                address: row.address,
                gstin: row.gstin,
                gst_state: row.gst_state,
                party_type: is_against_party ? row.party_type : null,
                party: is_against_party ? row.party : null,
            }));

            frappe.call({
                method: "india_compliance.gst_india.utils.isd.bulk_create_isd_distribution_invoices",
                args: {
                    purchase_invoice: purchase_invoice.name,
                    distribution_table: payload,
                    posting_date,
                    total_turnover,
                },
                freeze: true,
                freeze_message: __("Creating ISD Distribution Invoices..."),
                callback(r) {
                    const { invoices = [], failed = [] } = r.message || {};
                    if (!invoices.length && !failed.length) return;

                    const msg = [];
                    if (invoices.length)
                        msg.push(__("{0} ISD Distribution Invoices created as drafts.", [invoices.length]));
                    if (failed.length)
                        msg.push(
                            __("Could not create an invoice for {0}. Check the Error Logs for details", [
                                failed.join(", "),
                            ]),
                        );

                    frappe.msgprint({
                        title: __("ISD Distribution Invoices Created"),
                        message: msg.join("<br>"),
                        indicator: failed.length ? "orange" : "green",
                        primary_action_label: invoices.length ? __("View Invoices") : null,
                        primary_action: invoices.length
                            ? {
                                  action() {
                                      frappe.route_options = { name: ["in", invoices] };
                                      frappe.set_route("List", "ISD Distribution Invoice");
                                  },
                              }
                            : null,
                    });
                },
            });
        },
    });

    function render_summary(s) {
        const currency = erpnext.get_currency(company);
        const pct = s.total_tax ? (s.distributed_tax / s.total_tax) * 100 : 0;
        dialog.fields_dict.purchase_invoice_summary.$wrapper.html(`
            <table class="table table-bordered table-condensed" style="margin-bottom:0">
                <tbody>
                    <tr><th>${__("Purchase Invoice")}</th><td>${frappe.utils.escape_html(
                        s.purchase_invoice || purchase_invoice.name,
                    )}</td>
                        <th>${__("Supplier")}</th><td>${frappe.utils.escape_html(s.supplier || "")}</td></tr>
                    <tr><th>${__("Total Tax")}</th><td>${format_currency(s.total_tax || 0, currency)}</td>
                        <th>${__("Available to Distribute")}</th><td>${format_currency(
                            s.available_tax || 0,
                            currency,
                        )}</td></tr>
                    <tr><th>${__("Already Distributed")}</th><td>${format_currency(
                        s.distributed_tax || 0,
                        currency,
                    )}</td>
                        <th>${__("Distributed (%)")}</th><td>${pct.toFixed(2)}%</td></tr>
                </tbody>
            </table>
        `);
    }

    const distribution_grid = dialog.fields_dict.distribution_table.grid;

    dialog.show();
    render_summary({});

    // frappe does not fire a grid trigger on row removal, but the grid triggers "change" on the
    // wrapper once it has re-rendered (Grid.remove_rows -> Grid.refresh)
    distribution_grid.wrapper.on("click", ".grid-remove-rows", () => {
        distribution_grid.wrapper.one("change", () => {
            fill_total_turnover();
            calculate_distribution_ratios();
        });
    });

    frappe.call({
        method: "india_compliance.gst_india.utils.isd.get_purchase_invoice_distribution_summary",
        args: { purchase_invoice: purchase_invoice.name },
        async: true,
        callback: ({ message }) => message && render_summary(message),
    });

    let fetched_period = null;

    function fetch_and_prefill_grid() {
        const posting_date = dialog.get_value("posting_date") || frappe.datetime.get_today();
        frappe.call({
            method: "india_compliance.gst_india.utils.isd.get_distribution_addresses",
            args: {
                party_type: "Company",
                party: company,
                company,
                pi_posting_date: posting_date,
            },
            callback({ message: { addresses: rows = [], relevant_period } = {} }) {
                const period = String(relevant_period);
                if (period === fetched_period) return;

                fetched_period = period;
                if (!rows.length) return;
                distribution_grid.df.data = rows.map((r) => ({
                    party_type: "Company",
                    party: company,
                    address: r.name,
                    ...r,
                }));
                distribution_grid.refresh();
                fill_total_turnover();
                calculate_distribution_ratios();
            },
        });
    }

    function fill_total_turnover() {
        const rows = dialog.get_value("distribution_table") || [];
        const total = rows.reduce((sum, row) => sum + (parseFloat(row.turnover_amount) || 0), 0);
        dialog.set_value("total_turnover", total);
    }

    function calculate_distribution_ratios() {
        const rows = dialog.get_value("distribution_table") || [];
        const total = parseFloat(dialog.get_value("total_turnover")) || 0;

        rows.forEach((row) => {
            row.distribution_ratio = total ? ((parseFloat(row.turnover_amount) || 0) / total) * 100 : 0;
        });
        distribution_grid.refresh();
    }

    fetch_and_prefill_grid();
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
            for (const field of ["total_expense", "distributed_expense", "expense_head"]) {
                grid.update_docfield_property(field, "hidden", hidden);
            }
            this.frm.refresh_field("source_items");
        }
    }

    setup() {
        this.set_queries();
        this.load_company_defaults();
    }

    async load_company_defaults() {
        await this.fetch_gst_accounts();
        await this.fetch_company_defaults();
        if (this.frm.is_new()) {
            this.set_available_taxes();
            this.set_default_expense_head();
        }
    }

    set_default_expense_head() {
        if (!this.distribute_expense) return;

        for (const row of this.frm.doc.source_items || []) {
            if (!row.expense_head) row.expense_head = this.default_expense_account;
        }

        this.frm.refresh_field("source_items");
    }

    set_available_taxes() {
        // seed the taxes table with every configured input GST head with amount 0 to give familiar UI
        const accounts = this.gst_accounts || {};
        const existing = Object.fromEntries((this.frm.doc.taxes || []).map((tax) => [tax.gst_tax_type, tax]));

        for (const t of frappe.boot.gst_tax_types) {
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

    clear_credit_note_against() {
        if (this.frm.doc.is_credit_note || !this.frm.doc.credit_note_against) return;

        return this.frm.set_value("credit_note_against", null);
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

        frm.set_query("company_address", () => this._address_query("company_address"));
        frm.set_query("party_address", () => this._address_query("party_address"));

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
                    company_gstin: frm.doc.company_gstin,
                },
            }));
            frm.set_query("credit_note_against", () => ({
                filters: { docstatus: 1, company: frm.doc.company, is_credit_note: 0 },
            }));
        } else {
            frm.set_query("isd_distribution_invoice_reference", () => ({
                filters: {
                    docstatus: 1,
                    // company/party invert on the distribution invoice
                    company_gstin: frm.doc.party_gstin,
                    party_gstin: frm.doc.company_gstin,
                },
            }));
            frm.set_query("credit_note_against", () => ({
                filters: { docstatus: 1, company: frm.doc.company, is_credit_note: 0 },
            }));
        }
    }

    _address_query(field) {
        const frm = this.frm;
        // the ISD registration is the company's own address when distributing, the party's when receiving
        const isd_field = this.is_distribution_side ? "company_address" : "party_address";
        const category_op = field === isd_field ? "=" : "!=";
        const extra = [["gst_category", category_op, "Input Service Distributor"]];

        if (!frm.doc.company) {
            frappe.show_alert({ message: __("Please set Company first"), indicator: "orange" });
            return india_compliance.get_address_query("", "", extra);
        }

        // company_address is always linked to frm.doc.company
        if (!frm.doc.is_against_party || field === "company_address") {
            return india_compliance.get_address_query("Company", frm.doc.company, extra);
        }

        if (!frm.doc.party_type || !frm.doc.party) {
            frappe.show_alert({
                message: __("Please set Party Type and Party first"),
                indicator: "orange",
            });
            return india_compliance.get_address_query("", "", extra);
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
                    party_address: frm.doc.party_address || null,
                    posting_date: frm.doc.posting_date || null,
                    branch_turnover: frm.doc.branch_turnover || null,
                },
            },
        });

        if (!message || !Object.keys(message).length) return;

        frm.__updating_isd_autofill = true;
        try {
            await frm.set_value(message);
        } finally {
            frm.__updating_isd_autofill = false;
        }
    }

    // ------------------------------------------------------------------ address display / pos
    set_address_display(address_field, display_field) {
        erpnext.utils.get_address_display(this.frm, address_field, display_field);
    }

    async set_place_of_supply(address_field, pos_field) {
        const address = this.frm.doc[address_field];
        if (!address) {
            this.frm.set_value(pos_field, "");
            return;
        }
        const { message } = await frappe.call({
            method: "india_compliance.gst_india.utils.isd.get_isd_place_of_supply",
            args: { address },
        });
        this.frm.set_value(pos_field, message || "");
    }

    // ------------------------------------------------------------------ distribution preview
    async is_inter_state_distribution() {
        const frm = this.frm;

        // SEZ / overseas recipient is always inter-state (IGST), regardless of place of supply
        const recipient_address = this.is_distribution_side ? frm.doc.party_address : frm.doc.company_address;

        if (recipient_address) {
            const { message } = await frappe.db.get_value("Address", recipient_address, "gst_category");
            if (frappe.boot.import_gst_categories.includes(message?.gst_category)) return true;
        }

        // the comparison is symmetric, so it holds whichever side the company is on
        if (frm.doc.company_pos && frm.doc.party_pos) return frm.doc.company_pos !== frm.doc.party_pos;

        return false;
    }

    calculate_distribution_ratio() {
        const { branch_turnover, total_turnover } = this.frm.doc;

        if (flt(branch_turnover) < 0 || flt(total_turnover) < 0) {
            frappe.throw(__("Turnover cannot be negative"));
        }

        const distribution_ratio = total_turnover ? (flt(branch_turnover) / flt(total_turnover)) * 100 : 0;
        if (distribution_ratio > 100) {
            frappe.throw(__("Distribution Ratio cannot be greater than 100%"));
        }

        this.frm.set_value("distribution_ratio", distribution_ratio);
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
                (Math.abs(flt(row.total_igst)) +
                    Math.abs(flt(row.total_cgst)) +
                    Math.abs(flt(row.total_sgst))) *
                    ratio,
                _p,
            );
            row.distributed_cgst = 0;
            row.distributed_sgst = 0;
        } else {
            // intra-state -> each credit keeps its type (Rule 39(1)(e), (f))
            row.distributed_igst = flt(Math.abs(flt(row.total_igst)) * ratio, _p);
            row.distributed_cgst = flt(Math.abs(flt(row.total_cgst)) * ratio, _p);
            row.distributed_sgst = flt(Math.abs(flt(row.total_sgst)) * ratio, _p);
        }

        row.distributed_cess = flt(Math.abs(flt(row.total_cess)) * ratio, _p);
        row.distributed_cess_non_advol = flt(Math.abs(flt(row.total_cess_non_advol)) * ratio, _p);
        row.distributed_expense = this.distribute_expense
            ? flt(Math.abs(flt(row.total_expense)) * ratio, _pe)
            : 0;
    }

    async recalculate() {
        if (this.is_distribution_side && (this.frm.doc.source_items || []).length) {
            const inter_state = await this.is_inter_state_distribution();
            for (const row of this.frm.doc.source_items) {
                this._calculate_distribution_row(row, inter_state);
            }

            this.frm.refresh_field("source_items");
        }

        this.calculate_taxes_and_totals();
    }

    calculate_taxes_and_totals() {
        const rows = this.frm.doc.source_items || [];
        const distribution_side = this.is_distribution_side;
        const ratio = this.signed_ratio;

        const totals = Object.fromEntries(frappe.boot.gst_tax_types.map((t) => [t, 0]));
        let total_eligible = 0,
            total_ineligible = 0,
            total_expense = 0;

        for (const r of rows) {
            const _p = precision("distributed_igst", r);
            let row_total = 0;
            for (const t of frappe.boot.gst_tax_types) {
                row_total += r[`distributed_${t}`] || 0;

                totals[t] += distribution_side
                    ? flt(Math.abs(flt(r[`total_${t}`])) * ratio, _p)
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

        this.set_grand_total();
    }

    set_grand_total() {
        const { total_eligible, total_ineligible, total_expense } = this.frm.doc;

        this.frm.doc.grand_total = flt(total_eligible) + flt(total_ineligible) + flt(total_expense);
        this.frm.refresh_field("grand_total");
    }

    set_tax_amounts(totals) {
        const accounts = this.gst_accounts || {};
        const existing = Object.fromEntries((this.frm.doc.taxes || []).map((tax) => [tax.gst_tax_type, tax]));

        for (const t of frappe.boot.gst_tax_types) {
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

    async fetch_company_defaults() {
        if (!this.frm.doc.company) return;
        const { message } = await frappe.db.get_value("Company", this.frm.doc.company, [
            "cost_center",
            "default_expense_account",
        ]);
        this.default_cost_center = message?.cost_center || null;
        this.default_expense_account = message?.default_expense_account || null;
    }

    set_common_buttons() {
        if (this.frm.doc.docstatus >= 1) {
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
