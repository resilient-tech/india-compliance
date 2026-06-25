india_compliance.ISD_GST_CATEGORY = "Input Service Distributor";

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
    // { purchase invoice name: { supplier, posting_date, total_tax, available } } from the distribution summary
    let summary_by_pi = {};
    const company = purchase_invoice.company;

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
                fieldtype: "Column Break",
                fieldname: "column_1",
            },
            {
                fieldtype: "Check",
                fieldname: "is_against_party",
                label: __("Against Party"),
                default: 0,
                change() {
                    const hidden = !this.get_value();
                    distribution_grid.update_docfield_property("party_type", "hidden", hidden);
                    distribution_grid.update_docfield_property("party", "hidden", hidden);
                    distribution_grid.reset_grid();
                    distribution_grid.refresh();
                },
            },
            {
                fieldtype: "Column Break",
                fieldname: "column_2",
            },
            {
                fieldtype: "Date",
                fieldname: "posting_date",
                label: __("Posting Date"),
                default: frappe.datetime.get_today(),
                reqd: 1,
            },
            {
                fieldtype: "Section Break",
                fieldname: "address_section",
            },
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
                        reqd: 1,
                        columns: 2,
                        get_query(doc) {
                            return india_compliance.get_address_query(doc.party_type, doc.party);
                        },
                        async change() {
                            const { address, party_type, party } = this.doc;
                            if (!address) return;
                            const { posting_date: posting_date } = dialog.get_values();

                            frappe.call({
                                method: "india_compliance.gst_india.utils.isd.get_distribution_addresses",
                                args: { party_type, party, posting_date: posting_date, address },
                                callback: ({ message: [row] = [] }) => {
                                    if (!row) return;
                                    const { gstin, gst_category, gst_state, turnover_amount } = row;
                                    Object.assign(this.doc, {
                                        gstin,
                                        gst_category,
                                        gst_state,
                                        turnover_amount,
                                    });
                                    distribution_grid.fields_map.turnover_amount.change(); //trigger distribution_ratio recalculation
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
                        required: 1,
                        change() {
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
        primary_action_label: __("Create ISD Invoices"),
        primary_action() {
            const values = dialog.get_values();
            if (!values) return;
            const { distribution_table = [], is_against_party, posting_date } = values;
            const rows_with_turnover = distribution_table.filter((row) => row.turnover_amount);

            dialog.hide();

            const fiscal_year = erpnext.utils.get_fiscal_year(posting_date, company);
            const payload = rows_with_turnover.map((row) => ({
                ...row,
                fiscal_year: fiscal_year.name,
                turnover_amount: parseFloat(row.turnover_amount) || 0,
                party_address: row.address,
                party_type: is_against_party ? row.party_type : null,
                party: is_against_party ? row.party : null,
            }));

            frappe.call({
                method: "india_compliance.gst_india.utils.isd.bulk_create_isd_invoices",
                args: {
                    distribution_table: payload,
                    purchase_invoices: [purchase_invoice.name],
                    posting_date: posting_date,
                },
                freeze: true,
                freeze_message: __("Creating ISD Invoices..."),
                callback(r) {
                    if (!r.message) return;
                    const [invoices, invalid] = r.message;

                    if (!invalid.length && !invoices.length) {
                        frappe.msgprint({ title: __("No ISD Invoices Created"), indicator: "red" });
                        return;
                    }

                    frappe.msgprint({
                        title: __("ISD Invoices Created"),
                        message: invalid.length
                            ? __("Some ISD Invoices failed validations \n Check {0} for details", [
                                  invalid.join(", "),
                              ])
                            : __("{0} ISD Invoices created successfully", [invoices.length]),
                        indicator: invalid.length ? "orange" : "green",
                        primary_action_label: __("View ISD Invoices"),
                        primary_action: {
                            action() {
                                frappe.route_options = { name: ["in", invoices.concat(invalid)] };
                                frappe.set_route("List", "ISD Invoice");
                            },
                        },
                    });
                },
            });
        },
    });

    function render_summary(summary) {
        const currency = erpnext.get_currency(company);
        const escape_html = (value) => frappe.utils.escape_html(String(value ?? ""));
        let total_tax = 0;
        let total_available = 0;

        const rows_html = Object.entries(summary)
            .map(([pi_name, s]) => {
                const tt = s.total_tax ?? 0;
                const available = s.available ?? tt;
                const pct = tt > 0 ? ((tt - available) / tt) * 100 : 0;
                total_tax += tt;
                total_available += available;
                return `<tr>
                    <td>${escape_html(pi_name)}</td>
                    <td>${frappe.datetime.str_to_user(s.posting_date)}</td>
                    <td>${escape_html(s.supplier)}</td>
                    <td style="text-align:right">${format_currency(tt, currency)}</td>
                    <td style="text-align:right">${format_currency(available, currency)}</td>
                    <td style="text-align:right">${pct.toFixed(2)}%</td>
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
                    <th style="text-align:right">${__("Available to Distribute")}</th>
                    <th style="text-align:right">${__("Distributed (%)")}</th>
                </tr></thead>
                <tbody>${rows_html}</tbody>
                <tfoot><tr>
                    <td colspan="3"><strong>${__("Total")}</strong></td>
                    <td style="text-align:right"><strong>${format_currency(total_tax, currency)}</strong></td>
                    <td style="text-align:right"><strong>${format_currency(
                        total_available,
                        currency,
                    )}</strong></td>
                    <td></td>
                </tr></tfoot>
            </table>
        `);
    }

    const distribution_grid = (() => dialog.fields_dict.distribution_table.grid)();

    dialog.show();
    render_summary({});

    // fix needed in frappe, grid does not have remove row trigger
    distribution_grid.wrapper.on("click", ".grid-remove-rows", () => {
        setTimeout(() => {
            calculate_distribution_ratios();
        }, 1000); //1 sec taken by frappe to remove the rows
    });

    frappe.call({
        method: "india_compliance.gst_india.utils.isd.get_purchase_invoices_distribution_summary",
        args: { purchase_invoices: [purchase_invoice.name], extra_fields: ["supplier", "company"] },
        callback({ message: rows = [] }) {
            const p = (v) => parseFloat(v) || 0; //common float parser
            summary_by_pi = {};
            rows.forEach((x) => {
                const pi = x.purchase_invoice;
                if (!summary_by_pi[pi]) summary_by_pi[pi] = { total_tax: 0, available: 0 };
                summary_by_pi[pi].supplier = x.supplier;
                summary_by_pi[pi].posting_date = x.posting_date;
                summary_by_pi[pi].total_tax += p(x.total_tax);
                summary_by_pi[pi].available += p(x.available_tax);
            });
            render_summary(summary_by_pi);
        },
    });

    function fetch_and_prefill_grid() {
        // runs synchronously right after dialog.show(), before the async default-setting
        // promise resolves, so read the single value with a fallback instead of get_values()
        const posting_date = dialog.get_value("posting_date") || frappe.datetime.get_today();
        frappe.call({
            method: "india_compliance.gst_india.utils.isd.get_distribution_addresses",
            args: { party_type: "Company", party: company, posting_date: posting_date },
            callback({ message: rows = [] }) {
                if (!rows.length) return;
                distribution_grid.df.data = rows.map((r) => ({
                    party_type: "Company",
                    party: company,
                    address: r.name,
                    ...r,
                }));
                distribution_grid.refresh();
                calculate_distribution_ratios();
            },
        });
    }

    function calculate_distribution_ratios() {
        const values = dialog.get_values();
        const total_turnover = values?.distribution_table.reduce(
            (sum, row) => sum + (parseFloat(row.turnover_amount) || 0),
            0,
        );
        values?.distribution_table.forEach((row) => {
            row.distribution_ratio = total_turnover
                ? ((parseFloat(row.turnover_amount) || 0) / total_turnover) * 100
                : 0;
        });
        distribution_grid.refresh();
    }

    fetch_and_prefill_grid();
};
