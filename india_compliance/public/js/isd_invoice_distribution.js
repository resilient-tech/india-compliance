india_compliance.show_isd_invoice_distribution_dialog = function (purchase_invoices) {
    // purchase_invoices: [{ name, posting_date, supplier, company, total_tax }]
    const is_single = purchase_invoices.length === 1;
    const source_names = purchase_invoices.map((p) => p.name);
    const company = purchase_invoices[0].company;
    const posting_date = purchase_invoices[0].posting_date;

    let fetch_addresses = () => {};
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
                    let grid = dialog.fields_dict.distribution_heads.grid;
                    grid.update_docfield_property("party_type", "hidden", !this.get_value());
                    grid.update_docfield_property("party", "hidden", !this.get_value());
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
                        get_query: function (doc) {
                            let party_type = doc.party_type;
                            let search_text = doc.party || "";
                            return {
                                query: "india_compliance.gst_india.utils.get_party_for_isd",
                                params: {
                                    filters: {
                                        doctype: party_type,
                                        search_text: search_text,
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
                        get_query: function (doc) {
                            return {
                                query: "frappe.contacts.doctype.address.address.address_query",
                                filters: {
                                    link_doctype: doc.party_type,
                                    link_name: doc.party,
                                },
                            };
                        },
                        change: async function () {
                            const address = this.doc.address;
                            const party_type = this.doc.party_type;
                            const party = this.doc.party;
                            const grid = dialog.fields_dict.distribution_heads.grid;
                            const row = this.doc;

                            if (!address) return;

                            frappe.call({
                                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_distribution_heads",
                                args: {
                                    party_type: party_type,
                                    party: party,
                                    posting_date: posting_date,
                                    address: address,
                                },
                                callback: (r) => {
                                    if (r.message && r.message.length > 0) {
                                        row.gstin = r.message[0].gstin;
                                        row.gst_category = r.message[0].gst_category;
                                        row.gst_state = r.message[0].gst_state;
                                        row.turnover_amount = r.message[0].turnover_amount;
                                        grid.fields_map.turnover_amount.change();
                                        grid.refresh_row(row.idx);
                                    }
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
                        change: function () {
                            let grid = this.grid || dialog.fields_dict.distribution_heads.grid;
                            let total_turnover = grid.data.reduce(
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
        primary_action(values) {
            const dialog_values = dialog.get_values();
            const distribution_heads = dialog_values.distribution_heads || [];
            const rows_with_turnover = distribution_heads.filter((row) => row.turnover_amount);

            if (!rows_with_turnover.length) {
                frappe.msgprint(__("Please enter Turnover Amount for at least one row."), __("No Turnover"));
                return;
            }

            dialog.hide();

            const payload = rows_with_turnover.map((row) => {
                const turnover_amount = parseFloat(row.turnover_amount) || 0;
                return {
                    fiscal_year: erpnext.utils.get_fiscal_year(posting_date),
                    gstin: row.gstin || "",
                    gst_state: row.gst_state || "",
                    gst_category: row.gst_category || "",
                    turnover_amount: turnover_amount,
                    party_address: row.address,
                    party_type: dialog_values.is_against_party ? row.party_type : null,
                    party: dialog_values.is_against_party ? row.party : null,
                };
            });

            frappe.call({
                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.bulk_create_isd_invoices",
                args: {
                    distribution_heads: payload,
                    source_names: source_names,
                },
                callback(r) {
                    const { message } = r;
                    const success = message[0];
                    const invalid = message[1];

                    if (!invalid.length && !success.length) {
                        frappe.msgprint({
                            title: __("No ISD Invoices Created"),
                            indicator: "red",
                        });
                        return;
                    }

                    let msgprint_message = "ISD Invoices creation completed\n";
                    let indicator = "green";
                    if (invalid.length) {
                        indicator = "orange";
                        msgprint_message +=
                            "Some ISD Invoices failed validations. Please check " +
                            invalid.join(", ") +
                            " for details.\n";
                    }
                    frappe.msgprint({
                        title: "ISD Invoices Created",
                        message: msgprint_message,
                        indicator: indicator,
                        primary_action_label: __("View ISD Invoices"),
                        primary_action: {
                            action(values) {
                                frappe.route_options = {
                                    name: ["in", success.concat(invalid)],
                                };
                                frappe.set_route("List", "ISD Invoice");
                            },
                        },
                    });
                },
            });
        },
    });

    fetch_addresses = function () {
        frappe.call({
            method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_distribution_heads",
            args: {
                party_type: "Company",
                party: company,
                posting_date: posting_date,
            },
            callback(r) {
                if (!r.message) return;
                const data = r.message.map((row) => ({
                    party_type: "Company",
                    party: company,
                    address: row.name,
                    gstin: row.gstin,
                    gst_category: row.gst_category,
                    gst_state: row.gst_state,
                    turnover_amount: row.turnover_amount,
                }));
                const grid = dialog.fields_dict.distribution_heads.grid;
                grid.df.data = data;
                grid.refresh();
                grid.fields_map.turnover_amount.change();
            },
        });
    };

    dialog.show();

    const summary_wrapper = dialog.fields_dict.purchase_invoice_summary.$wrapper;
    const currency = frappe.boot.sysdefaults.currency;

    function render_summary(dist_map) {
        const rows_html = purchase_invoices
            .map((pi) => {
                const total = (dist_map[pi.name] || {}).total_tax ?? pi.total_tax ?? 0;
                const distributed = (dist_map[pi.name] || {}).total_distributed || pi.total_distributed || 0;
                const pct = total > 0 ? Math.min((distributed / total) * 100, 100) : 0;
                const pct_label = pct.toFixed(1) + "%";
                const text_color = pct > 50 ? "#fff" : "#333";
                return `<tr>
                    <td>${pi.name}</td>
                    <td>${frappe.datetime.str_to_user(pi.posting_date)}</td>
                    <td>${pi.supplier || ""}</td>
                    <td style="text-align:right">${format_currency(total, currency)}</td>
                    <td style="min-width:140px; vertical-align:middle;">
                        <div style="position:relative;">
                            <div class="progress" style="height:20px; margin:0; border-radius:3px; background-color:#dee2e6;">
                                <div class="progress-bar bg-success" role="progressbar"
                                    style="width:${pct.toFixed(1)}%; border-radius:3px;"
                                    aria-valuenow="${pct.toFixed(1)}" aria-valuemin="0" aria-valuemax="100">
                                </div>
                            </div>
                            <span style="position:absolute; top:0; left:0; right:0; text-align:center;
                                line-height:20px; font-size:12px; font-weight:500; color:${text_color}; pointer-events:none;">
                                ${pct_label}
                            </span>
                        </div>
                    </td>
                </tr>`;
            })
            .join("");
        const total_tax = purchase_invoices.reduce((sum, p) => {
            return sum + ((dist_map[p.name] || {}).total_tax ?? p.total_tax ?? 0);
        }, 0);
        summary_wrapper.html(`
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

    render_summary({});

    frappe.call({
        method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_purchase_invoices_distribution_summary",
        args: { purchase_invoices: source_names, posting_date: posting_date },
        callback(r) {
            if (!r.message) return;
            const dist_map = {};
            for (const row of r.message) dist_map[row.purchase_invoice] = row;
            render_summary(dist_map);
        },
    });

    if (is_single) fetch_addresses();
};
