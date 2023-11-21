frappe.ui.form.on("Journal Entry", {
    company: set_gstin_options,
});

async function set_gstin_options(frm) {
    const options = await india_compliance.get_gstin_options(frm.doc.company);
	frm.get_field("company_gstin").set_data(options);

    frm.set_value("company_gstin", options.length === 1 ? options[0] : "");
}

frappe.ui.form.on("Journal Entry Account", {
    account: toggle_gstin_for_journal_entry,
    accounts_remove: toggle_gstin_for_journal_entry,
});

function toggle_gstin_for_journal_entry(frm) {
    toggle_company_gstin(frm, taxes_table="accounts", account_head="account");
}

async function toggle_company_gstin(frm, taxes_table, account_head) {
    _toggle_company_gstin(frm, await contains_gst_account(frm, taxes_table, account_head));
}

async function contains_gst_account(frm, taxes_table, account_field) {
    if (!frm.gst_accounts || frm.company !== frm.doc.company) {
        frm.gst_accounts = await india_compliance.get_account_options(frm.doc.company);
        frm.company = frm.doc.company;
    }

    return frm.doc[taxes_table].some(row => frm.gst_accounts.includes(row[account_field]));
}

function _toggle_company_gstin(frm, reqd) {
    if (frm.get_field("company_gstin").df.reqd !== reqd) {
        frm.set_df_property("company_gstin", "reqd", reqd);
        frm.refresh_field("company_gstin");
    }
}
