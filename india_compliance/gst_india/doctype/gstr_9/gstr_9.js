// Copyright (c) 2025, Resilient Tech and contributors
// For license information, please see license.txt

frappe.provide("india_compliance");

const DOCTYPE = "GSTR-9";

// Amount columns for Tables 4-8
const AMOUNT_COLUMNS = [
    { label: "Taxable Value", fieldname: "taxable_value" },
    { label: "IGST", fieldname: "igst" },
    { label: "CGST", fieldname: "cgst" },
    { label: "SGST/UTGST", fieldname: "sgst" },
    { label: "Cess", fieldname: "cess" },
];

// Row descriptions
const ROW_DESCRIPTIONS = {
    "4A": "Supplies made to un-registered persons (B2C)",
    "4B": "Supplies made to registered persons (B2B)",
    "4C": "Zero rated supply (Export) on payment of tax (except supplies to SEZs)",
    "4D": "Supply to SEZs on payment of tax",
    "4E": "Deemed Exports",
    "4F": "Advances on which tax has been paid but invoice has not been issued (not covered under (4A) to (4E) above)",
    "4G": "Inward supplies on which tax is to be paid on reverse charge basis",
    "4G1": "Supplies on which e-commerce operator is required to pay tax u/s 9(5) [Operator to report]",
    "4H": "Sub-total (4A to 4G1)",
    "4I": "Credit Notes issued in respect of transactions in (4B) to (4E)",
    "4J": "Debit Notes issued in respect of transactions in (4B) to (4E)",
    "4K": "Supplies / tax declared through Amendments (+)",
    "4L": "Supplies / tax declared through Amendments (-)",
    "4M": "Sub-total (4I to 4L)",
    "4N": "Supplies and advances on which tax is to be paid (4H + 4M) above",
    "5A": "Zero rated supply (Export) without payment of tax",
    "5B": "Supply to SEZs without payment of tax",
    "5C": "Supplies on which tax is to be paid by the recipient on reverse charge basis",
    "5C1": "Supplies on which tax is to be paid by e-commerce operators u/s 9(5) [Supplier to report]",
    "5D": "Exempted",
    "5E": "Nil Rated",
    "5F": "Non-GST supply (includes 'no supply')",
    "5G": "Sub-total (5A to 5F)",
    "5H": "Credit Notes issued in respect of transactions in (5A) to (5F)",
    "5I": "Debit Notes issued in respect of transactions in (5A) to (5F)",
    "5J": "Supplies declared through Amendments (+)",
    "5K": "Supplies declared through Amendments (-)",
    "5L": "Sub-total (5H to 5K)",
    "5M": "Turnover on which tax is not to be paid  (5G + 5L) above",
    "5N": "Total Turnover (including advances) (4N + 5M - 4G - 4G1)",
    "6A": "Total amount of input tax credit availed through FORM GSTR-3B (Sum total of table 4A of FORM GSTR-3B)",
    "6A1": "ITC of any preceding financial year availed in the financial year (which is included in 6A above) other than reclaim",
    "6A2": "Net ITC of the financial year (A-A1)",
    "6B": "Inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs)",
    "6B_ip": "Inputs",
    "6B_cg": "Capital Goods",
    "6B_is": "Input Services",
    "6C": "Inward supplies received from unregistered persons liable to reverse charge (other than B above) on which tax is paid & ITC availed",
    "6C_ip": "Inputs",
    "6C_cg": "Capital Goods",
    "6C_is": "Input Services",
    "6D": "Inward supplies received from registered persons liable to reverse charge (other than B above) on which tax is paid and ITC availed",
    "6D_ip": "Inputs",
    "6D_cg": "Capital Goods",
    "6D_is": "Input Services",
    "6E": "Import of goods (including supplies from SEZ)",
    "6E_ip": "Inputs",
    "6E_cg": "Capital Goods",
    "6F": "Import of services (excluding inward supplies from SEZs)",
    "6G": "Input Tax credit received from ISD",
    "6H": "Amount of ITC reclaimed under the provisions of the Act",
    "6I": "Sub-total (B to H above)",
    "6J": "Difference (I - A2 above)",
    "6K": "Transition Credit through TRAN-1 (including revisions if any)",
    "6L": "Transition Credit through TRAN-2",
    "6M": "ITC availed through ITC-01, ITC-02, and ITC-02A (other than GSTR-3B and TRAN Forms)",
    "6N": "Sub-total (K to M above)",
    "6O": "Total ITC availed (I + N) above",
    "7A": "As per Rule 37",
    "7A1": "As per Rule 37A",
    "7A2": "As per Rule 38",
    "7B": "As per Rule 39",
    "7C": "As per Rule 42",
    "7D": "As per Rule 43",
    "7E": "As per section 17(5)",
    "7F": "Reversal of TRAN-I credit",
    "7G": "Reversal of TRAN-II credit",
    "7H1": "Other reversals (specify)",
    "7I": "Total ITC Reversed (A to H)",
    "7J": "Net ITC Available for Utilization (6O - 7I)",
    "8A": "ITC as per GSTR-2B",
    "8B": "ITC as per sum total of 6B above",
    "8C": "ITC on inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs) received during the financial year but availed in the next financial year upto specified period",
    "8D": "Difference [8A - (8B + 8C)]",
    "8E": "ITC available but not availed",
    "8F": "ITC available but ineligible",
    "8G": "IGST paid on import of goods",
    "8H": "IGST credit availed on import of goods (as per 6(E) above) in financial year",
    "8H1": "IGST Credit availed on Import of goods in next financial year",
    "8I": "Difference (8G - 8H - 8H1)",
    "8J": "ITC available but not availed on import of goods (Equal to 8I)",
    "8K": "Total ITC to be lapsed in current financial year (8E + 8F + 8J)",
    9: "Details of tax paid as declared in returns filed during the financial year",
    10: "Supplies / tax declared through Debit Notes (+)",
    11: "Supplies / tax reduced through Credit Notes (\u2013)",
    "10_11_turnover": "Turnover including adjustments above (5N + 10 \u2013 11)",
    12: "Reversal of ITC availed during previous financial year",
    13: "ITC availed for the previous financial year",
    14: "Differential tax paid on account of declaration in Table 10 & 11",
    15: "Particulars of Demands and Refunds",
    "16A": "Inward supplies received from composition taxpayers",
    "16B": "Deemed supply under Section 143(3) and (5) by Job Worker",
    "16C": "Goods sent on approval basis but not returned within 6 months",
};

// Auto-computed (non-editable) rows
const AUTO_COMPUTED_ROWS = new Set([
    "4H",
    "4M",
    "4N",
    "5G",
    "5L",
    "5M",
    "5N",
    "10_11_turnover",
    "6A2",
    "6I",
    "6J",
    "6N",
    "6O",
    "7I",
    "7J",
    "8B",
    "8D",
    "8H",
    "8I",
    "8J",
    "8K",
]);

// Portal-sourced (read-only) rows
const PORTAL_SOURCED_ROWS = new Set(["6A", "8A", "9"]);

// Rows not supported by books computation (manual/portal only)
const NOT_SUPPORTED_ROWS = new Set(["4G1", "4K", "4L", "5J", "5K"]);

// Rows that require manual entry by the user
const MANUAL_ENTRY_ROWS = new Set([
    "6A1",
    "6H",
    "6K",
    "6L",
    "6M",
    "7A",
    "7A1",
    "7A2",
    "7B",
    "7C",
    "7D",
    "7E",
    "7F",
    "7G",
    "7H1",
    "8C",
    "8E",
    "8F",
    "8G",
    "8H1",
]);

// Rows that support drill-down to individual invoice records (Books tab only)
const DETAIL_VIEW_ROWS = new Set([
    // Table 4 — Outward supplies (taxable)
    "4A",
    "4B",
    "4C",
    "4D",
    "4E",
    "4G",
    "4I",
    "4J",
    // Table 5 — Outward supplies (non-taxable)
    "5A",
    "5B",
    "5C",
    "5C1",
    "5D",
    "5E",
    "5F",
    "5H",
    "5I",
    // Table 6 — ITC availed (inward)
    "6B",
    "6B_ip",
    "6B_cg",
    "6B_is",
    "6C",
    "6C_ip",
    "6C_cg",
    "6C_is",
    "6D",
    "6D_ip",
    "6D_cg",
    "6D_is",
    "6E",
    "6E_ip",
    "6E_cg",
    "6F",
    "6G",
]);

// Cells that are not applicable for a row — rendered with white background
// Map of row_key → Set of disabled fieldnames
const DISABLED_CELLS = {
    "4C": new Set(["cgst", "sgst"]),
    "4D": new Set(["cgst", "sgst"]),
    "5A": new Set(["igst", "cgst", "sgst", "cess"]),
    "5B": new Set(["igst", "cgst", "sgst", "cess"]),
    "5C": new Set(["igst", "cgst", "sgst", "cess"]),
    "5C1": new Set(["igst", "cgst", "sgst", "cess"]),
    "5D": new Set(["igst", "cgst", "sgst", "cess"]),
    "5E": new Set(["igst", "cgst", "sgst", "cess"]),
    "5F": new Set(["igst", "cgst", "sgst", "cess"]),
    "5G": new Set(["igst", "cgst", "sgst", "cess"]),
    "5H": new Set(["igst", "cgst", "sgst", "cess"]),
    "5I": new Set(["igst", "cgst", "sgst", "cess"]),
    "5J": new Set(["igst", "cgst", "sgst", "cess"]),
    "5K": new Set(["igst", "cgst", "sgst", "cess"]),
    "5L": new Set(["igst", "cgst", "sgst", "cess"]),
    "5M": new Set(["igst", "cgst", "sgst", "cess"]),
    "6E": new Set(["cgst", "sgst"]),
    "6E_ip": new Set(["cgst", "sgst"]),
    "6E_cg": new Set(["cgst", "sgst"]),
    "6F": new Set(["cgst", "sgst"]),
    "6K": new Set(["igst", "cess"]),
    "6L": new Set(["igst", "cess"]),
    "7F": new Set(["igst", "cess"]),
    "7G": new Set(["igst", "cess"]),
    "8F": new Set(["igst", "cess"]),
    "8G": new Set(["igst", "cess"]),
};

// Table sections for grouping rows in the UI
const TABLE_SECTIONS = [
    {
        title: "Part II — Table 4: Outward Supplies (Tax Payable)",
        rows: [
            "4A",
            "4B",
            "4C",
            "4D",
            "4E",
            "4F",
            "4G",
            "4G1",
            "4H",
            "4I",
            "4J",
            "4K",
            "4L",
            "4M",
            "4N",
        ],
    },
    {
        title: "Part II — Table 5: Outward Supplies (Tax Not Payable)",
        rows: [
            "5A",
            "5B",
            "5C",
            "5C1",
            "5D",
            "5E",
            "5F",
            "5G",
            "5H",
            "5I",
            "5J",
            "5K",
            "5L",
            "5M",
            "5N",
        ],
    },
    {
        title: "Part III — Table 6: ITC Availed",
        hide_taxable_value: true,
        has_type_column: true,
        rows: [
            "6A",
            "6A1",
            "6A2",
            "6B",
            "6C",
            "6D",
            "6E",
            "6F",
            "6G",
            "6H",
            "6I",
            "6J",
            "6K",
            "6L",
            "6M",
            "6N",
            "6O",
        ],
        bifurcated_rows: {
            "6B": ["6B_ip", "6B_cg", "6B_is"],
            "6C": ["6C_ip", "6C_cg", "6C_is"],
            "6D": ["6D_ip", "6D_cg", "6D_is"],
            "6E": ["6E_ip", "6E_cg"],
        },
    },
    {
        title: "Part III — Table 7: ITC Reversed",
        hide_taxable_value: true,
        hidden: true,
        rows: [
            "7A",
            "7A1",
            "7A2",
            "7B",
            "7C",
            "7D",
            "7E",
            "7F",
            "7G",
            "7H1",
            "7I",
            "7J",
        ],
    },
    {
        title: "Part III — Table 8: Other ITC Related Information",
        hide_taxable_value: true,
        hidden: true,
        rows: ["8A", "8B", "8C", "8D", "8E", "8F", "8G", "8H", "8H1", "8I", "8J", "8K"],
    },
    {
        title: "Part IV — Table 9: Tax Paid",
        hidden: true,
        rows: ["9"],
    },
    {
        title: "Part V — Tables 10 & 11: Transactions for Previous FY Declared in Current FY",
        hidden: true,
        rows: ["10", "11", "10_11_turnover"],
    },
    {
        title: "Part V — Tables 12 & 13: ITC Adjustments for Previous FY",
        hide_taxable_value: true,
        hidden: true,
        rows: ["12", "13"],
    },
    {
        title: "Part V — Table 14: Differential Tax Paid",
        hidden: true,
        rows: ["14"],
        is_table_14: true,
    },
    {
        title: "Part VI — Table 15: Demands and Refunds",
        hidden: true,
        rows: ["15"],
        is_table_15: true,
    },
    {
        title: "Part VI — Table 16: Composition Taxpayers / Deemed Supply / Approval Basis",
        hidden: true,
        rows: ["16A", "16B", "16C"],
    },
    {
        title: "Part VI — Table 17: HSN-wise Summary of Outward Supplies",
        rows: ["17"],
        is_hsn: true,
    },
    {
        title: "Part VI — Table 18: HSN-wise Summary of Inward Supplies",
        rows: ["18"],
        is_hsn: true,
    },
];

// =====================================
// Form Events
// =====================================

frappe.ui.form.on(DOCTYPE, {
    async setup(frm) {
        frm.gstr9 = new GSTR9(frm);

        // Set defaults
        frm.doc.company = frappe.defaults.get_user_default("Company");
        frm.trigger("company");

        // Setup realtime listeners
        frappe.realtime.on("gstr9_data_prepared", message => {
            const { filters } = message;

            if (
                frm.doc.company_gstin !== filters?.company_gstin ||
                frm.doc.financial_year !== filters?.financial_year
            )
                return;

            frm.taxpayer_api_call("generate_gstr9").then(r => {
                if (!r.message) return;
                frm.doc.__gst_data = r.message;
                frm.trigger("load_gstr9_data");
            });
        });

        frappe.realtime.on("gstr9_generation_failed", message => {
            const { error, filters } = message;
            frappe.msgprint({
                title: __("GSTR-9 Generation Failed"),
                message: __("GSTR-9 generation failed for {0} - {1}.<br/><br/>{2}", [
                    filters?.company_gstin || "",
                    filters?.financial_year || "",
                    error || "",
                ]),
                indicator: "red",
            });
        });

        frappe.realtime.on("show_missing_gst_credentials_message", message => {
            frappe.msgprint(message);
        });

        frm.__setup_complete = true;
    },

    async company(frm) {
        render_empty_state(frm);
        if (!frm.doc.company) return;
        const options = await india_compliance.set_gstin_options(frm, false, true);
        frm.set_value("company_gstin", options?.[0]);
    },

    company_gstin(frm) {
        render_empty_state(frm);
    },

    financial_year(frm) {
        render_empty_state(frm);
    },

    refresh(frm) {
        frm.disable_save();
        frm.gstr9?.render_form_actions();

        if (!frm.doc.__gst_data) {
            frm.page.clear_indicator();
            return;
        }

        frm.gstr9.render_indicator();
    },

    load_gstr9_data(frm) {
        const data = frm.doc.__gst_data;
        if (!data?.status) return;

        frm.refresh();
        frm.gstr9.status = data.status;
        frm.gstr9.refresh_data(data);
    },
});

function render_empty_state(frm) {
    frm.doc.__gst_data = null;
    frm.refresh();
}

function format_currency(value) {
    return format_number(value, null, 2);
}

class GSTR9 {
    TABS = [
        { label: __("Books"), name: "books", is_active: true },
        { label: __("Portal"), name: "portal" },
        { label: __("Comparison"), name: "comparison" },
    ];

    constructor(frm) {
        this.init(frm);
        this.render();
    }

    init(frm) {
        this.frm = frm;
        this.data = null;
        this.status = null;
        this.$wrapper = frm.fields_dict.tabs_html.$wrapper;
    }

    refresh_data(data) {
        if (data) this.data = data;

        this.TABS.forEach(_tab => {
            const tab_name = _tab.name;
            const tab = this.tabs[`${tab_name}_tab`];
            const tab_data = this._get_tab_data(tab_name);

            if (!tab_data) {
                tab.hide();
                _tab.shown = false;
                return;
            }

            tab.show();
            _tab.shown = true;

            const $html = this.tab_group.get_field(`${tab_name}_html`).$wrapper;
            this._render_tab_content($html, tab_name, tab_data);
        });
    }

    _get_tab_data(tab_name) {
        if (!this.data) return null;

        if (tab_name === "books") return this.data.books_summary;
        if (tab_name === "portal") return this.data.portal_summary;
        if (tab_name === "comparison") return this.data.comparison;

        return null;
    }

    // ───── Render ─────

    render() {
        this._render_tab_group();
        this._setup_detail_view_listeners();
    }

    _render_tab_group() {
        const tab_fields = this.TABS.reduce(
            (acc, tab) => [
                ...acc,
                {
                    fieldtype: "Tab Break",
                    fieldname: `${tab.name}_tab`,
                    label: __(tab.label),
                    active: tab.is_active ? 1 : 0,
                },
                {
                    fieldtype: "HTML",
                    fieldname: `${tab.name}_html`,
                },
            ],
            [],
        );

        this.tab_group = new frappe.ui.FieldGroup({
            fields: [{ fieldtype: "Section Break" }, ...tab_fields],
            body: this.$wrapper,
            frm: this.frm,
        });
        this.tab_group.make();

        this.tabs = Object.fromEntries(
            this.tab_group.tabs.map(tab => [tab.df.fieldname, tab]),
        );

        // Remove padding around content
        this.$wrapper.closest(".form-column").css("padding", "0px");
        this.$wrapper.closest(".row.form-section").css("padding", "0px");
    }

    _render_tab_content($wrapper, tab_name, data) {
        $wrapper.empty();

        if (tab_name === "comparison") {
            this._render_comparison_tab($wrapper, data);
            return;
        }

        // Books or Portal tab — summary rows
        this._render_summary_tab($wrapper, data, tab_name);
    }

    _render_summary_tab($wrapper, summary_rows, tab_name) {
        if (!summary_rows?.length) {
            $wrapper.html(
                `<div class="text-muted text-center" style="padding: 40px;">
                    ${__("No data available")}
                </div>`,
            );
            return;
        }

        // Build row lookup for quick access
        const row_map = {};
        for (const row of summary_rows) {
            row_map[row.row_key] = row;
        }

        for (const section of TABLE_SECTIONS) {
            if (section.hidden) continue;

            // Table 14 — custom payable/paid/difference column structure
            if (section.is_table_14) {
                const row = row_map["14"];
                if (!row) continue;
                $wrapper.append(this._build_table_14_html(section.title, row));
                continue;
            }

            // Table 15 — custom 7-component column structure
            if (section.is_table_15) {
                const row = row_map["15"];
                if (!row) continue;
                $wrapper.append(this._build_table_15_html(section.title, row));
                continue;
            }

            // HSN section: render Goods (Part A) and Services (Part B) sub-tables
            if (section.is_hsn) {
                const hsn_key = section.rows[0];
                const hsn_row = row_map[hsn_key];
                if (!hsn_row) continue;
                const has_data =
                    (hsn_row.goods?.length || 0) + (hsn_row.services?.length || 0) > 0;
                if (!has_data) continue;
                $wrapper.append(this._build_hsn_section_html(section.title, hsn_row));
                continue;
            }

            const section_rows = section.rows
                .filter(key => row_map[key])
                .map(key => row_map[key]);

            if (!section_rows.length) continue;

            // Special handling for Table 9
            if (section.rows.includes("9")) {
                $wrapper.append(this._build_table_9_html(section.title, row_map["9"]));
                continue;
            }

            const section_cols =
                section.custom_columns ||
                (section.hide_taxable_value
                    ? AMOUNT_COLUMNS.filter(c => c.fieldname !== "taxable_value")
                    : AMOUNT_COLUMNS);

            if (section.bifurcated_rows) {
                $wrapper.append(
                    this._build_section_with_type_column_html(
                        section,
                        section_rows,
                        row_map,
                        tab_name === "books",
                        section_cols,
                    ),
                );
            } else {
                $wrapper.append(
                    this._build_section_html(
                        section.title,
                        section_rows,
                        tab_name === "books",
                        section_cols,
                    ),
                );
            }
        }
    }

    _render_comparison_tab($wrapper, comparison) {
        if (!comparison || !Object.keys(comparison).length) {
            $wrapper.html(
                `<div class="text-muted text-center" style="padding: 40px;">
                    ${__("No differences found between Books and Portal data")}
                </div>`,
            );
            return;
        }

        let html = `<div class="gstr9-comparison">`;

        for (const section of TABLE_SECTIONS) {
            if (section.hidden) continue;
            if (section.is_hsn) continue; // HSN tables excluded from comparison

            // For bifurcated sections, check sub-rows for differences
            let keys_to_check;
            if (section.bifurcated_rows) {
                keys_to_check = section.rows.flatMap(key => {
                    const subs = section.bifurcated_rows[key];
                    return subs ? subs : [key];
                });
            } else {
                keys_to_check = section.rows;
            }

            const section_diffs = keys_to_check.filter(key => comparison[key]);
            if (!section_diffs.length) continue;

            const cmp_cols =
                section.custom_columns ||
                (section.hide_taxable_value
                    ? AMOUNT_COLUMNS.filter(c => c.fieldname !== "taxable_value")
                    : AMOUNT_COLUMNS);

            html += `<div class="gstr9-section">
                <h6 class="gstr9-section-title">${__(section.title)}</h6>
                <div class="table-responsive">
                    <table class="table table-bordered gstr9-table">
                        <thead>
                            <tr>
                                <th class="gstr9-col-sno">${__("S.No")}</th>
                                <th class="gstr9-col-desc">${__("Description")}</th>
                                <th class="gstr9-col-source">${__("Source")}</th>`;

            for (const col of cmp_cols) {
                html += `<th class="text-right">${__(col.label)}</th>`;
            }

            html += `</tr></thead><tbody>`;

            for (const row_key of section_diffs) {
                const diff = comparison[row_key];
                const desc = ROW_DESCRIPTIONS[row_key] || row_key;

                // Books row
                html += `<tr class="gstr9-comparison-books">
                    <td rowspan="3" class="gstr9-col-sno">${row_key}</td>
                    <td rowspan="3" class="gstr9-col-desc">${__(desc)}</td>
                    <td class="gstr9-col-source"><span class="badge badge-info">${__("Books")}</span></td>`;
                for (const col of cmp_cols) {
                    html += `<td class="text-right">${format_currency(diff.books?.[col.fieldname] || 0)}</td>`;
                }
                html += `</tr>`;

                // Portal row
                html += `<tr class="gstr9-comparison-portal">
                    <td class="gstr9-col-source"><span class="badge badge-warning">${__("Portal")}</span></td>`;
                for (const col of cmp_cols) {
                    html += `<td class="text-right">${format_currency(diff.portal?.[col.fieldname] || 0)}</td>`;
                }
                html += `</tr>`;

                // Difference row
                html += `<tr class="gstr9-comparison-diff">
                    <td class="gstr9-col-source"><strong>${__("Diff")}</strong></td>`;
                for (const col of cmp_cols) {
                    const val = diff.difference?.[col.fieldname] || 0;
                    const cls = val > 0 ? "text-danger" : val < 0 ? "text-success" : "";
                    html += `<td class="text-right ${cls}"><strong>${format_currency(val)}</strong></td>`;
                }
                html += `</tr>`;
            }

            html += `</tbody></table></div></div>`;
        }

        html += `</div>`;
        $wrapper.html(html);
    }

    _build_section_with_type_column_html(
        section,
        rows,
        row_map,
        is_books = false,
        columns = AMOUNT_COLUMNS,
    ) {
        const bifurcated_rows = section.bifurcated_rows || {};

        let html = `<div class="gstr9-section">
            <h6 class="gstr9-section-title">${__(section.title)}</h6>
            <div class="table-responsive">
                <table class="table table-bordered gstr9-table">
                    <thead>
                        <tr>
                            <th class="gstr9-col-sno">${__("S.No")}</th>
                            <th class="gstr9-col-desc">${__("Description")}</th>
                            <th>${__("Type")}</th>`;

        for (const col of columns) {
            html += `<th class="text-right">${__(col.label)}</th>`;
        }

        html += `</tr></thead><tbody>`;

        for (const row of rows) {
            const row_key = row.row_key;
            const is_auto = AUTO_COMPUTED_ROWS.has(row_key);
            const is_portal = PORTAL_SOURCED_ROWS.has(row_key);
            const is_manual_entry = MANUAL_ENTRY_ROWS.has(row_key);
            let row_class = "";
            if (is_auto) row_class = "gstr9-row-auto";
            else if (is_portal || is_manual_entry) row_class = "gstr9-row-portal";

            const sub_row_keys = bifurcated_rows[row_key];

            if (sub_row_keys) {
                // Bifurcated: description cell spans sub-rows, each sub-row gets a Type cell
                const rowspan = sub_row_keys.length;
                html += `<tr>
                    <td class="gstr9-col-sno" rowspan="${rowspan}">${row_key}</td>
                    <td class="gstr9-col-desc" rowspan="${rowspan}">`;

                if (is_books && DETAIL_VIEW_ROWS.has(row_key)) {
                    html += `<a href="#" class="gstr9-detail-link"
                        data-row-key="${row_key}"
                        data-description="${(row.description || "").replace(/"/g, "&quot;")}"
                        >${__(row.description)}</a>`;
                } else {
                    html += `${__(row.description)}`;
                }

                if (is_portal) {
                    html += ` <span class="badge badge-warning">${__("Portal")}</span>`;
                }

                html += `</td>`;

                // Render each sub-row (always normal background, no inherited row_class)
                for (let i = 0; i < sub_row_keys.length; i++) {
                    const sub_key = sub_row_keys[i];
                    const sub_row = row_map[sub_key] || {};
                    const sub_disabled = DISABLED_CELLS[sub_key];

                    if (i > 0) html += `<tr>`;

                    // Use static ROW_DESCRIPTIONS as primary label (always available)
                    const type_label =
                        ROW_DESCRIPTIONS[sub_key] || sub_row.description || "";

                    if (is_books && DETAIL_VIEW_ROWS.has(sub_key)) {
                        html += `<td><a href="#" class="gstr9-detail-link"
                            data-row-key="${sub_key}"
                            data-description="${(row.description || "").replace(/"/g, "&quot;")} - ${type_label.replace(/"/g, "&quot;")}"
                            >${__(type_label)}</a></td>`;
                    } else {
                        html += `<td>${__(type_label)}</td>`;
                    }

                    for (const col of columns) {
                        if (sub_disabled?.has(col.fieldname)) {
                            html += `<td class="gstr9-cell-disabled"></td>`;
                        } else {
                            html += `<td class="text-right">${format_currency(sub_row[col.fieldname] || 0)}</td>`;
                        }
                    }

                    html += `</tr>`;
                }
            } else {
                // Regular row: empty Type cell
                html += `<tr class="${row_class}">
                    <td class="gstr9-col-sno">${row_key}</td>
                    <td class="gstr9-col-desc">`;

                if (is_books && DETAIL_VIEW_ROWS.has(row_key)) {
                    html += `<a href="#" class="gstr9-detail-link"
                        data-row-key="${row_key}"
                        data-description="${(row.description || "").replace(/"/g, "&quot;")}"
                        >${__(row.description)}</a>`;
                } else {
                    html += `${__(row.description)}`;
                }

                if (is_portal) {
                    html += ` <span class="badge badge-warning">${__("Portal")}</span>`;
                }
                if (is_manual_entry) {
                    html += ` <span class="badge badge-primary">${__("Manual Entry")}</span>`;
                }

                html += `</td><td></td>`; // empty Type cell

                const disabled = DISABLED_CELLS[row_key];
                for (const col of columns) {
                    if (disabled?.has(col.fieldname)) {
                        html += `<td class="gstr9-cell-disabled"></td>`;
                    } else {
                        html += `<td class="text-right">${format_currency(row[col.fieldname] || 0)}</td>`;
                    }
                }

                html += `</tr>`;
            }
        }

        html += `</tbody></table></div></div>`;
        return html;
    }

    _build_section_html(title, rows, is_books = false, columns = AMOUNT_COLUMNS) {
        let html = `<div class="gstr9-section">
            <h6 class="gstr9-section-title">${__(title)}</h6>
            <div class="table-responsive">
                <table class="table table-bordered gstr9-table">
                    <thead>
                        <tr>
                            <th class="gstr9-col-sno">${__("S.No")}</th>
                            <th class="gstr9-col-desc">${__("Description")}</th>`;

        for (const col of columns) {
            html += `<th class="text-right">${__(col.label)}</th>`;
        }

        html += `</tr></thead><tbody>`;

        for (const row of rows) {
            const is_auto = AUTO_COMPUTED_ROWS.has(row.row_key);
            const is_portal = PORTAL_SOURCED_ROWS.has(row.row_key);
            const is_not_supported = NOT_SUPPORTED_ROWS.has(row.row_key);
            const is_manual_entry = MANUAL_ENTRY_ROWS.has(row.row_key);
            let row_class = "";
            if (is_auto) row_class = "gstr9-row-auto";
            else if (is_portal || is_not_supported || is_manual_entry)
                row_class = "gstr9-row-portal";

            html += `<tr class="${row_class}">
                <td class="gstr9-col-sno">${row.row_key}</td>
                <td class="gstr9-col-desc">`;

            if (is_books && DETAIL_VIEW_ROWS.has(row.row_key)) {
                html += `<a href="#" class="gstr9-detail-link"
                    data-row-key="${row.row_key}"
                    data-description="${(row.description || "").replace(/"/g, "&quot;")}"
                    >${__(row.description)}</a>`;
            } else {
                html += `${__(row.description)}`;
            }

            if (is_portal) {
                html += ` <span class="badge badge-warning">${__("Portal")}</span>`;
            }
            if (is_not_supported) {
                html += ` <span class="badge badge-secondary">${__("Not Supported")}</span>`;
            }
            if (is_manual_entry) {
                html += ` <span class="badge badge-primary">${__("Manual Entry")}</span>`;
            }

            html += `</td>`;

            const disabled = DISABLED_CELLS[row.row_key];
            for (const col of columns) {
                if (disabled?.has(col.fieldname)) {
                    html += `<td class="gstr9-cell-disabled"></td>`;
                } else {
                    html += `<td class="text-right">${format_currency(row[col.fieldname] || 0)}</td>`;
                }
            }

            html += `</tr>`;
        }

        html += `</tbody></table></div></div>`;
        return html;
    }

    _build_table_9_html(title, row_data) {
        const rows = (row_data && row_data.rows) || [];
        // Table 9 ITC sub-columns (Paid through ITC breakdown)
        const TABLE_9_ITC_COLUMNS = [
            { label: "IGST", fieldname: "itc_igst" },
            { label: "CGST", fieldname: "itc_cgst" },
            { label: "SGST/UTGST", fieldname: "itc_sgst" },
            { label: "Cess", fieldname: "itc_cess" },
        ];

        let html = `<div class="gstr9-section">
            <h6 class="gstr9-section-title">${__(title)}</h6>`;

        if (rows.length) {
            // Two-row header: row-1 has main cols + "Paid through ITC" spanning 4;
            // row-2 has the 4 ITC sub-cols.
            const itc_span = TABLE_9_ITC_COLUMNS.length;
            html += `<div class="table-responsive">
                <table class="table table-bordered gstr9-table">
                    <thead>
                        <tr>
                            <th rowspan="2" class="gstr9-col-sno">${__("S.No")}</th>
                            <th rowspan="2" class="gstr9-col-desc">${__("Description")}</th>
                            <th rowspan="2" class="text-right">${__("Tax Payable (₹)")}</th>
                            <th rowspan="2" class="text-right">${__("Paid through Cash (₹)")}</th>
                            <th colspan="${itc_span}" class="text-center">${__("Paid through ITC (₹)")}</th>
                            <th rowspan="2" class="text-right">${__("Total Tax Paid (₹)")}</th>
                            <th rowspan="2" class="text-right">${__("Difference (₹)")}</th>
                        </tr>
                        <tr>`;

            for (const col of TABLE_9_ITC_COLUMNS) {
                html += `<th class="text-right">${__(col.label)}</th>`;
            }

            html += `</tr>
                    </thead>
                    <tbody>`;

            rows.forEach(row => {
                html += `<tr class="gstr9-row-portal">
                    <td>${row.row_label || ""}</td>
                    <td>${__(row.tax_head || "")}</td>
                    <td class="text-right">${format_currency(row.tax_payable || 0)}</td>
                    <td class="text-right">${format_currency(row.paid_through_cash || 0)}</td>`;

                for (const col of TABLE_9_ITC_COLUMNS) {
                    html += `<td class="text-right">${format_currency(row[col.fieldname] || 0)}</td>`;
                }

                html += `
                    <td class="text-right">${format_currency(row.total_paid || 0)}</td>
                    <td class="text-right">${format_currency(row.difference || 0)}</td>
                </tr>`;
            });

            html += `</tbody></table></div>`;
        } else {
            html += `<div class="text-muted text-center" style="padding: 20px;">
                ${__("Table 9 data will be available after downloading portal data")}
            </div>`;
        }

        html += `</div>`;
        return html;
    }

    _build_table_14_html(title, row_data) {
        const rows = (row_data && row_data.rows) || [];

        let html = `<div class="gstr9-section">
            <h6 class="gstr9-section-title">${__(title)}</h6>
            <div class="table-responsive">
                <table class="table table-bordered gstr9-table">
                    <thead>
                        <tr>
                            <th class="gstr9-col-sno">${__("S.No")}</th>
                            <th class="gstr9-col-desc">${__("Description")}</th>
                            <th class="text-right">${__("Payable (₹)")}</th>
                            <th class="text-right">${__("Paid (₹)")}</th>
                            <th class="text-right">${__("Difference (₹)")}</th>
                        </tr>
                    </thead>
                    <tbody>`;

        for (const row of rows) {
            const diff = flt(row.payable || 0) - flt(row.paid || 0);
            html += `<tr>
                <td class="gstr9-col-sno">${row.label || ""}</td>
                <td class="gstr9-col-desc">${__(row.description || "")}</td>
                <td class="text-right">${format_currency(row.payable || 0)}</td>
                <td class="text-right">${format_currency(row.paid || 0)}</td>
                <td class="text-right">${format_currency(diff)}</td>
            </tr>`;
        }

        html += `</tbody></table></div></div>`;
        return html;
    }

    _build_table_15_html(title, row_data) {
        const rows = (row_data && row_data.rows) || [];

        const T15_COLS = [
            { label: __("IGST"), fieldname: "igst" },
            { label: __("CGST"), fieldname: "cgst" },
            { label: __("SGST/UTGST"), fieldname: "sgst" },
            { label: __("Cess"), fieldname: "cess" },
            { label: __("Interest"), fieldname: "interest" },
            { label: __("Penalty"), fieldname: "penalty" },
            { label: __("Late Fee / Others"), fieldname: "late_fee" },
        ];

        let html = `<div class="gstr9-section">
            <h6 class="gstr9-section-title">${__(title)}</h6>
            <div class="table-responsive">
                <table class="table table-bordered gstr9-table">
                    <thead>
                        <tr>
                            <th class="gstr9-col-sno">${__("S.No")}</th>
                            <th class="gstr9-col-desc">${__("Details")}</th>`;

        for (const col of T15_COLS) {
            html += `<th class="text-right">${col.label}</th>`;
        }

        html += `</tr></thead><tbody>`;

        for (const row of rows) {
            html += `<tr>
                <td class="gstr9-col-sno">${row.label || ""}</td>
                <td class="gstr9-col-desc">${__(row.description || "")}</td>`;

            for (const col of T15_COLS) {
                html += `<td class="text-right">${format_currency(row[col.fieldname] || 0)}</td>`;
            }

            html += `</tr>`;
        }

        html += `</tbody></table></div></div>`;
        return html;
    }

    _build_hsn_section_html(title, hsn_row) {
        const goods = (hsn_row && hsn_row.goods) || [];
        const services = (hsn_row && hsn_row.services) || [];

        let html = `<div class="gstr9-section">
            <h6 class="gstr9-section-title">${__(title)}</h6>`;

        if (goods.length) {
            html += this._build_hsn_sub_table_html(__("Part A - Goods"), goods, false);
        }
        if (services.length) {
            html += this._build_hsn_sub_table_html(
                __("Part B - Services"),
                services,
                true,
            );
        }

        html += `</div>`;
        return html;
    }

    _build_hsn_sub_table_html(subtitle, rows, is_service) {
        // Goods cols: S.No | HSN | Desc | UQC | Qty | Rate | Taxable | IGST | CGST | SGST | Cess (11)
        // Service cols: S.No | HSN | Desc | Rate | Taxable | IGST | CGST | SGST | Cess (9)
        const total_colspan = is_service ? 4 : 6; // cols before taxable_value in totals row

        let html = `<h6 class="gstr9-hsn-subtitle">${subtitle}</h6>
            <div class="table-responsive">
                <table class="table table-bordered gstr9-table">
                    <thead>
                        <tr>
                            <th class="gstr9-col-sno">${__("S.No.")}</th>
                            <th>${__("HSN/SAC")}</th>
                            <th>${__("Description")}</th>`;

        if (!is_service) {
            html += `<th>${__("UQC")}</th>
                            <th class="text-right">${__("Total Quantity")}</th>`;
        }

        html += `<th class="text-right">${__("Tax Rate")}</th>
                            <th class="text-right">${__("Taxable Value")}</th>
                            <th class="text-right">${__("IGST")}</th>
                            <th class="text-right">${__("CGST")}</th>
                            <th class="text-right">${__("SGST/UTGST")}</th>
                            <th class="text-right">${__("Cess")}</th>
                        </tr>
                    </thead>
                    <tbody>`;

        const totals = { taxable_value: 0, igst: 0, cgst: 0, sgst: 0, cess: 0 };

        rows.forEach((row, idx) => {
            const hsn_link = row.hsn_code
                ? `<a href="${frappe.utils.get_form_link("GST HSN Code", row.hsn_code)}">${row.hsn_code}</a>`
                : "";
            html += `<tr>
                <td class="gstr9-col-sno">${idx + 1}</td>
                <td>${hsn_link}</td>
                <td>${row.description || ""}</td>`;

            if (!is_service) {
                html += `<td>${row.uom || ""}</td>
                <td class="text-right">${format_number(row.quantity || 0, null, 3)}</td>`;
            }

            html += `<td class="text-right">${flt(row.tax_rate || 0, 2)}%</td>
                <td class="text-right">${format_currency(row.taxable_value || 0)}</td>
                <td class="text-right">${format_currency(row.igst || 0)}</td>
                <td class="text-right">${format_currency(row.cgst || 0)}</td>
                <td class="text-right">${format_currency(row.sgst || 0)}</td>
                <td class="text-right">${format_currency(row.cess || 0)}</td>
            </tr>`;

            for (const f of ["taxable_value", "igst", "cgst", "sgst", "cess"]) {
                totals[f] += row[f] || 0;
            }
        });

        html += `<tr class="gstr9-row-auto">
            <td colspan="${total_colspan}" class="text-right"><strong>${__("Total")}</strong></td>
            <td class="text-right"><strong>${format_currency(totals.taxable_value)}</strong></td>
            <td class="text-right"><strong>${format_currency(totals.igst)}</strong></td>
            <td class="text-right"><strong>${format_currency(totals.cgst)}</strong></td>
            <td class="text-right"><strong>${format_currency(totals.sgst)}</strong></td>
            <td class="text-right"><strong>${format_currency(totals.cess)}</strong></td>
        </tr>`;

        html += `</tbody></table></div>`;
        return html;
    }

    // ───── Detail view ─────

    _setup_detail_view_listeners() {
        this.$wrapper.on("click", ".gstr9-detail-link", async e => {
            e.preventDefault();
            const $link = $(e.currentTarget);
            const row_key = $link.data("row-key");
            const description = $link.data("description");
            await this.show_invoice_detail(String(row_key), String(description));
        });
    }

    async show_invoice_detail(row_key, description) {
        frappe.show_alert(__("Loading details…"));

        let result;
        try {
            const r = await frappe.call({
                method: "india_compliance.gst_india.doctype.gstr_9.gstr_9.get_gstr9_invoice_detail",
                args: {
                    company_gstin: this.frm.doc.company_gstin,
                    financial_year: this.frm.doc.financial_year,
                    row_key,
                },
            });
            result = r.message;
        } catch (e) {
            frappe.msgprint(__("Failed to load detail data."));
            return;
        }

        if (result && result.too_large) {
            frappe.msgprint({
                title: __("Large Dataset — Export Required"),
                message: __(
                    "The books data file is too large to display inline. Use the Export Books as Excel button to download all invoices.",
                ),
                indicator: "orange",
            });
            return;
        }

        this._show_detail_dialog(
            row_key,
            description,
            result || { is_purchase: false, data: [] },
        );
    }

    _show_detail_dialog(row_key, description, result) {
        const { is_purchase, data } = result;

        if (!data || !data.length) {
            frappe.msgprint({
                title: __("No Records"),
                message: __("No records found for {0} — {1}", [
                    row_key,
                    __(description),
                ]),
            });
            return;
        }

        const route = is_purchase ? "purchase-invoice" : "sales-invoice";
        const party_gstin_label = is_purchase
            ? __("Supplier GSTIN")
            : __("Customer GSTIN");
        const party_name_label = is_purchase
            ? __("Supplier Name")
            : __("Customer Name");
        const doc_label = is_purchase ? __("Bill No.") : __("Invoice No.");
        const class_label = is_purchase ? __("Classification") : __("Type");

        const totals = {
            total_taxable_value: 0,
            total_igst_amount: 0,
            total_cgst_amount: 0,
            total_sgst_amount: 0,
            total_cess_amount: 0,
        };

        const party_gstin_field = is_purchase ? "supplier_gstin" : "customer_gstin";
        const party_name_field = is_purchase ? "supplier_name" : "customer_name";

        const rows = data.map(row => {
            totals.total_taxable_value += row.total_taxable_value || 0;
            totals.total_igst_amount += row.total_igst_amount || 0;
            totals.total_cgst_amount += row.total_cgst_amount || 0;
            totals.total_sgst_amount += row.total_sgst_amount || 0;
            totals.total_cess_amount += row.total_cess_amount || 0;

            return {
                document_date: frappe.datetime.str_to_user(row.document_date) || "",
                document_number: row.document_number,
                doc_route: row.doc_route || route,
                party_gstin: row[party_gstin_field] || "",
                party_name: row[party_name_field] || "",
                type_label: row.transaction_type || "",
                total_taxable_value: row.total_taxable_value || 0,
                total_igst_amount: row.total_igst_amount || 0,
                total_cgst_amount: row.total_cgst_amount || 0,
                total_sgst_amount: row.total_sgst_amount || 0,
                total_cess_amount: row.total_cess_amount || 0,
            };
        });

        const currency_fields = new Set([
            "total_taxable_value",
            "total_igst_amount",
            "total_cgst_amount",
            "total_sgst_amount",
            "total_cess_amount",
        ]);

        const fmt_currency = value => format_currency(value || 0);

        const columns = [
            {
                id: "document_date",
                name: __("Date"),
                field: "document_date",
                width: 100,
            },
            {
                id: "document_number",
                name: doc_label,
                field: "document_number",
                width: 190,
                format: (value, _row, _col, data) =>
                    `<a href="/app/${data?.doc_route || route}/${encodeURIComponent(value || "")}" target="_blank">${frappe.utils.escape_html(value || "")}</a>`,
            },
            {
                id: "party_gstin",
                name: party_gstin_label,
                field: "party_gstin",
                width: 170,
            },
            {
                id: "party_name",
                name: party_name_label,
                field: "party_name",
                width: 180,
            },
            { id: "type_label", name: class_label, field: "type_label", width: 180 },
            {
                id: "total_taxable_value",
                name: __("Taxable Value"),
                field: "total_taxable_value",
                width: 130,
                align: "right",
                format: fmt_currency,
            },
            {
                id: "total_igst_amount",
                name: __("IGST"),
                field: "total_igst_amount",
                width: 110,
                align: "right",
                format: fmt_currency,
            },
            {
                id: "total_cgst_amount",
                name: __("CGST"),
                field: "total_cgst_amount",
                width: 110,
                align: "right",
                format: fmt_currency,
            },
            {
                id: "total_sgst_amount",
                name: __("SGST/UTGST"),
                field: "total_sgst_amount",
                width: 120,
                align: "right",
                format: fmt_currency,
            },
            {
                id: "total_cess_amount",
                name: __("Cess"),
                field: "total_cess_amount",
                width: 95,
                align: "right",
                format: fmt_currency,
            },
        ];

        const dialog = new frappe.ui.Dialog({
            title: `${row_key} — ${__(description)}`,
            size: "extra-large",
            fields: [{ fieldtype: "HTML", fieldname: "detail_content" }],
        });

        dialog.$wrapper.find(".modal-dialog").css("max-width", "95vw");

        const $wrapper = dialog.fields_dict.detail_content.$wrapper;
        // const $dt_wrapper = $('<div style="height:55vh; overflow:auto"></div>');
        const $dt_wrapper = $('<div style="overflow:auto"></div>');
        $wrapper.append($dt_wrapper);

        // Initialize DataTable only after the modal transition completes so the
        // container has real pixel dimensions — otherwise frappe.DataTable measures
        // zero width and renders nothing until a resize/filter forces a recalc.
        dialog.$wrapper.one("shown.bs.modal", () => {
            new frappe.DataTable($dt_wrapper.get(0), {
                columns,
                data: rows,
                showTotalRow: true,
                checkboxColumn: false,
                inlineFilters: true,
                noDataMessage: __("No data"),
                cellHeight: 34,
                layout: "fluid",
                hooks: {
                    columnTotal: (_col, row) => {
                        const id = row.column?.id;
                        if (id === "document_date") return __("{0}", ["Total"]);
                        if (currency_fields.has(id)) return totals[id] || 0;
                        return "";
                    },
                },
            });
        });

        dialog.show();
    }

    // ───── Indicator ─────

    render_indicator() {
        if (!this.status) {
            this.frm.page.clear_indicator();
            return;
        }

        const color = this.status === "Filed" ? "green" : "orange";
        this.frm.page.set_indicator(this.status, color);
    }

    // ───── Form Actions ─────

    render_form_actions() {
        this.frm.page.clear_actions();

        // Primary: Generate
        this.frm.page.set_primary_action(__("Generate"), () => {
            this.frm.taxpayer_api_call("generate_gstr9").then(r => {
                if (!r.message) return;
                this.frm.doc.__gst_data = r.message;
                this.frm.trigger("load_gstr9_data");
            });
        });

        // Custom buttons (only if data exists)
        if (this.data) {
            this.frm.add_custom_button(__("Recompute Books"), () => {
                if (this._recomputing) return;
                this._recomputing = true;
                this.frm
                    .taxpayer_api_call("recompute_books")
                    .then(r => {
                        if (!r.message) return;
                        this.frm.doc.__gst_data = r.message;
                        this.frm.trigger("load_gstr9_data");
                    })
                    .finally(() => {
                        this._recomputing = false;
                    });
            });

            this.frm.add_custom_button(__("Export Books as Excel"), () => {
                open_url_post(
                    "/api/method/india_compliance.gst_india.doctype.gstr_9.gstr_9.export_gstr9_books_as_excel",
                    {
                        company_gstin: this.frm.doc.company_gstin,
                        financial_year: this.frm.doc.financial_year,
                    },
                );
            });

            if (is_gstr9_api_enabled()) {
                this.frm.add_custom_button(__("Download Portal Data"), () => {
                    frappe.show_alert(__("Downloading portal data from GSTN..."));
                    this.frm.taxpayer_api_call("download_portal_data").then(r => {
                        if (!r.message) return;
                        this.frm.doc.__gst_data = r.message;
                        this.frm.trigger("load_gstr9_data");
                        frappe.show_alert({
                            message: __("Portal data downloaded successfully"),
                            indicator: "green",
                        });
                    });
                });
            }
        }
    }
}

function is_gstr9_api_enabled() {
    return (
        india_compliance.is_api_enabled() &&
        !gst_settings.sandbox_mode &&
        gst_settings.enable_gstr_9_api
    );
}
