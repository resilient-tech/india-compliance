frappe.ui.form.on("Item Tax Template", {
    refresh: show_missing_accounts_banner,
    fetch_gst_accounts: fetch_and_update_missing_gst_accounts,
});

async function show_missing_accounts_banner(frm) {
    if (frm.doc.gst_treatment === "Non-GST") return;

    const missing_accounts = await get_missing_gst_accounts(frm);
    if (!missing_accounts) return;

    // show banner
    frm.dashboard.add_comment(
        __(`<strong>Missing GST Accounts:</strong> ${missing_accounts.join(", ")}`),
        "orange",
        true
    );
}

async function fetch_and_update_missing_gst_accounts(frm) {
    const missing_accounts = await get_missing_gst_accounts(frm);
    if (!missing_accounts) return;

    const [_, intra_state_accounts, inter_state_accounts] =
        frm._company_gst_accounts[frm.doc.company];

    missing_accounts.forEach(account => {
        let tax_rate = 0;

        if (intra_state_accounts.includes(account)) tax_rate = frm.doc.gst_rate / 2;
        else if (inter_state_accounts.includes(account)) tax_rate = frm.doc.gst_rate;

        frm.add_child("taxes", { tax_type: account, tax_rate: tax_rate });
    });
    frm.refresh_field("taxes");
}

async function get_missing_gst_accounts(frm) {
    const company = frm.doc.company;

    // cache company gst accounts
    if (!frm._company_gst_accounts?.[company]) {
        frm._company_gst_accounts = frm._company_gst_accounts || {};
        const { message } = await frappe.call({
            method: "india_compliance.gst_india.overrides.transaction.get_valid_gst_accounts",
            args: { company: company },
        });

        frm._company_gst_accounts[company] = message;
    }

    if (!frm._company_gst_accounts[company]) return;

    const gst_accounts = frm._company_gst_accounts[company][0];
    const template_accounts = frm.doc.taxes.map(t => t.tax_type);
    const missing_accounts = gst_accounts.filter(
        a => a && !template_accounts.includes(a)
    );

    if (missing_accounts.length) return missing_accounts;
}
