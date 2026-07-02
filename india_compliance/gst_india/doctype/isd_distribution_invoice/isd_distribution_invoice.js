// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

const ISD_SOURCE_ITEM_READONLY_FIELDS = [
    "total_igst",
    "total_cgst",
    "total_sgst",
    "total_cess",
    "total_cess_non_advol",
    "distributed_igst",
    "distributed_cgst",
    "distributed_sgst",
    "distributed_cess",
    "distributed_cess_non_advol",
    "cost_center",
    "project",
    "expense_head",
    "total_expense",
    "distributed_expense",
];

frappe.ui.form.on("ISD Distribution Invoice", {
    refresh(frm) {
        const grid = frm.fields_dict.source_items.grid;
        // ISD_SOURCE_ITEM_READONLY_FIELDS.forEach(field => grid.toggle_enable(field, false));
    },
    branch_turnover: calculate_distribution_ratio,
    total_turnover: calculate_distribution_ratio,
});

function calculate_distribution_ratio(frm) {
    const { branch_turnover, total_turnover } = frm.doc;

    const distribution_ratio = total_turnover ? (flt(branch_turnover) / flt(total_turnover)) * 100 : 0;

    frm.set_value("distribution_ratio", distribution_ratio);
}
