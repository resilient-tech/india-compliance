india_compliance.show_isd_invoice_distribution_dialog = function (purchase_invoices) {
    // purchase_invoices: [{ name, posting_date, supplier, company, total_tax }]
    const is_single = purchase_invoices.length === 1;
    const purchase_invoice = purchase_invoices.map((p) => p.name);
    const company = purchase_invoices[0].company;
    const posting_date = purchase_invoices[0].posting_date;

    // last column will be too narrow, frappe issue #38228
    const dialog = new frappe.ui.Dialog({
        title: __("Select Addresses for ISD Distribution"),
        size: "extra-large",
        fields: [
            {
                fieldtype: "Section Break",
                fieldname: "purchase_invoice_section",
                label: __("Purchase Invoices Being Distributed"),
            },
            {
                fieldtype: "HTML",
                fieldname: "purchase_invoice_summary",
            },
            {
                fieldtype: "Section Break",
                fieldname: "general_section",
            },
            {
                fieldtype: "Check",
                fieldname: "is_against_party",
                label: __("Against Party"),
                default: 0,
                change() {
                    const grid = dialog.fields_dict.distribution_heads.grid;
                    const hidden = !this.get_value();
                    grid.update_docfield_property("party_type", "hidden", hidden);
                    grid.update_docfield_property("party", "hidden", hidden);
                    grid.reset_grid();
                    grid.refresh();
                },
            },
            {
                fieldtype: "Section Break",
                fieldname: "address_section",
            },
            {
                label: __("Distribution Heads"),
                fieldtype: "Table",
                fieldname: "distribution_heads",
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
                        fieldtype: "Autocomplete",
                        fieldname: "party",
                        label: __("Party"),
                        default: company,
                        in_list_view: 1,
                        columns: 2,
                        hidden: 1,
                        get_query(doc) {
                            return {
                                query: "india_compliance.gst_india.utils.get_party_for_isd",
                                params: {
                                    filters: {
                                        doctype: doc.party_type,
                                        search_text: doc.party || "",
                                        company: company,
                                    },
                                },
                            };
                        },
                    },
                    {
                        fieldtype: "Link",
                        options: "Address",
                        fieldname: "address",
                        label: __("Address"),
                        in_list_view: 1,
                        columns: 2,
                        get_query(doc) {
                            return {
                                query: "frappe.contacts.doctype.address.address.address_query",
                                filters: {
                                    link_doctype: doc.party_type,
                                    link_name: doc.party,
                                },
                            };
                        },
                        async change() {
                            const { address, party_type, party } = this.doc;
                            if (!address) return;

                            frappe.call({
                                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_distribution_addresses",
                                args: { party_type, party, posting_date, address },
                                callback: ({ message: [row] = [] }) => {
                                    if (!row) return;
                                    const { gstin, gst_category, gst_state, turnover_amount } = row;
                                    Object.assign(this.doc, {
                                        gstin,
                                        gst_category,
                                        gst_state,
                                        turnover_amount,
                                    });
                                    const grid = dialog.fields_dict.distribution_heads.grid;
                                    grid.fields_map.turnover_amount.change();
                                    grid.refresh_row(this.doc.idx);
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
                    {
                        fieldtype: "Data",
                        fieldname: "gst_category",
                        label: __("GST Category"),
                        read_only: 1,
                        in_list_view: 0,
                    },
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
                        label: __("Turnover Amount"),
                        in_list_view: 1,
                        default: 0,
                        columns: 2,
                        change() {
                            const grid = this.grid || dialog.fields_dict.distribution_heads.grid;
                            const total_turnover = grid.data.reduce(
                                (sum, row) => sum + (parseFloat(row.turnover_amount) || 0),
                                0,
                            );
                            grid.data.forEach((row) => {
                                row.distribution_ratio = total_turnover
                                    ? ((parseFloat(row.turnover_amount) || 0) / total_turnover) * 100
                                    : 0;
                            });
                            grid.refresh();
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
        primary_action_label: __("Create ISD Invoices"),
        primary_action() {
            const { distribution_heads = [], is_against_party } = dialog.get_values();
            const rows_with_turnover = distribution_heads.filter((row) => row.turnover_amount);

            if (!rows_with_turnover.length) {
                frappe.msgprint(__("Please enter Turnover Amount for at least one row."), __("No Turnover"));
                return;
            }

            dialog.hide();

            const payload = rows_with_turnover.map((row) => ({
                fiscal_year: erpnext.utils.get_fiscal_year(posting_date),
                gstin: row.gstin || "",
                gst_state: row.gst_state || "",
                gst_category: row.gst_category || "",
                turnover_amount: parseFloat(row.turnover_amount) || 0,
                party_address: row.address,
                party_type: is_against_party ? row.party_type : null,
                party: is_against_party ? row.party : null,
            }));

            frappe.call({
                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.bulk_create_isd_invoices",
                args: { distribution_heads: payload, purchase_invoices: purchase_invoice },
                freeze: true,
                freeze_message: __("Creating ISD Invoices..."),
                callback(r) {
                    if (!r.message) return;
                    const [success, invalid] = r.message;

                    if (!invalid.length && !success.length) {
                        frappe.msgprint({ title: __("No ISD Invoices Created"), indicator: "red" });
                        return;
                    }

                    frappe.msgprint({
                        title: __("ISD Invoices Created"),
                        message: invalid.length
                            ? __("Some ISD Invoices failed validations. Check {0} for details.", [
                                  invalid.join(", "),
                              ])
                            : __("ISD Invoices creation completed."),
                        indicator: invalid.length ? "orange" : "green",
                        primary_action_label: __("View ISD Invoices"),
                        primary_action: {
                            action() {
                                frappe.route_options = { name: ["in", success.concat(invalid)] };
                                frappe.set_route("List", "ISD Invoice");
                            },
                        },
                    });
                },
            });
        },
    });

    function render_summary(dist_map) {
        const currency = frappe.boot.sysdefaults.currency;
        let total_tax = 0;

        const rows_html = purchase_invoices
            .map((pi) => {
                const { total_tax: tt = pi.total_tax ?? 0, total_distributed: td = 0 } =
                    dist_map[pi.name] ?? {};
                total_tax += tt;
                const pct = tt > 0 ? Math.min((td / tt) * 100, 100) : 0;
                return `<tr>
                    <td>${pi.name}</td>
                    <td>${frappe.datetime.str_to_user(pi.posting_date)}</td>
                    <td>${pi.supplier || ""}</td>
                    <td style="text-align:right">${format_currency(tt, currency)}</td>
                    <td style="min-width:120px; vertical-align:middle;">
                        <div class="progress" style="margin:0">
                            <div class="progress-bar progress-bar-success" role="progressbar"
                                aria-valuenow="${Math.round(pct)}"
                                aria-valuemin="0" aria-valuemax="100"
                                style="width:${Math.round(pct)}%">
                            </div>
                        </div>
                        <span class="text-muted small">${pct.toFixed(1)}%</span>
                    </td>
                </tr>`;
            })
            .join("");

        dialog.fields_dict.purchase_invoice_summary.$wrapper.html(`
            <table class="table table-bordered table-condensed" style="margin-bottom:0">
                <thead><tr>
                    <th>${__("Purchase Invoice")}</th>
                    <th>${__("Posting Date")}</th>
                    <th>${__("Supplier")}</th>
                    <th style="text-align:right">${__("Total Tax")}</th>
                    <th>${__("Distributed")}</th>
                </tr></thead>
                <tbody>${rows_html}</tbody>
                <tfoot><tr>
                    <td colspan="3"><strong>${__("Total")}</strong></td>
                    <td style="text-align:right"><strong>${format_currency(total_tax, currency)}</strong></td>
                    <td></td>
                </tr></tfoot>
            </table>
        `);
    }

    dialog.show();
    render_summary({});

    frappe.call({
        method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_purchase_invoices_distribution_summary",
        args: { purchase_invoices: purchase_invoice },
        callback({ message: rows = [] }) {
            const p = (v) => parseFloat(v) || 0;
            const dist_map = Object.fromEntries(
                rows.map((x) => [
                    x.purchase_invoice,
                    {
                        total_tax: p(x.total_tax),
                        total_distributed: p(x.total_distributed),
                    },
                ]),
            );
            render_summary(dist_map);
        },
    });

    function fetch_and_prefill_grid() {
        frappe.call({
            method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_distribution_addresses",
            args: { party_type: "Company", party: company, posting_date },
            callback({ message: rows = [] }) {
                if (!rows.length) return;
                const grid = dialog.fields_dict.distribution_heads.grid;
                grid.df.data = rows.map((r) => ({
                    party_type: "Company",
                    party: company,
                    address: r.name,
                    ...r,
                }));
                grid.refresh();
                grid.fields_map.turnover_amount.change();
            },
        });
    }

    if (is_single) fetch_and_prefill_grid();
};
