frappe.ui.form.on("Journal Entry", {
    company: set_gstin_options,
});

async function set_gstin_options(frm) {
    const options = await ic.get_gstin_options(frm.doc.company);
    const gstin_field = frm.get_field("company_gstin");
    gstin_field.set_data(options);

    if (options.length == 1) frm.set_value("company_gstin", options[0]);
    else frm.set_value("company_gstin", "");
}

frappe.ui.form.on("Journal Entry Account", {
    account: toggle_company_gstin,
    accounts_remove: toggle_company_gstin,
});

async function toggle_company_gstin(frm) {
    if (await contains_gst_account(frm)) _toggle_company_gstin(frm, true);
    else _toggle_company_gstin(frm, false);
}

async function contains_gst_account(frm) {
    if (!frm.gst_accounts || frm.company != frm.doc.company) {
        frm.gst_accounts = await ic.get_account_options(frm.doc.company);
        frm.company = frm.doc.company;
    }

    return frm.doc.accounts.some(row => {
        if (frm.gst_accounts.includes(row.account)) return true;
    });
}

function _toggle_company_gstin(frm, reqd) {
    const gstin_field = frm.get_field("company_gstin");
    if (gstin_field.df.reqd == reqd) return;
    gstin_field.df.reqd = reqd;
    frm.refresh_field("company_gstin");
}
