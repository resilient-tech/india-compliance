frappe.ui.form.on("Expense Claim", {
    company: set_gstin_options,
});

frappe.ui.form.on("Expense Taxes and Charges", {
    account_head: toggle_gstin_for_expense_claim,
    accounts_head_remove: toggle_gstin_for_expense_claim,
});

function toggle_gstin_for_expense_claim(frm) {
	toggle_company_gstin(frm, taxes_table="taxes", account_field="account_head");
}