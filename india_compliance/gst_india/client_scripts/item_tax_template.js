frappe.ui.form.on("Item Tax Template", {
    refresh: show_missing_accounts_banner,
    fetch_gst_accounts: fetch_and_update_missing_gst_accounts,
    async gst_rate(frm) {
        if (frm.doc.gst_rate === null) return;

        await Promise.all(
            frm.doc.taxes.map(async row => {
                const tax_rate = await get_tax_rate_for_account(frm, row.tax_type);
                if (tax_rate == null) return;

                row.tax_rate = tax_rate;
            })
        );

        frm.refresh_field("taxes");
    },
});

async function show_missing_accounts_banner(frm) {
    if (frm.doc.gst_treatment === "Non-GST" || frm.doc.__islocal) return;

    const missing_accounts = await get_missing_gst_accounts(frm);
    if (!missing_accounts) return;

    // show banner
    frm.dashboard.add_comment(
        __(`<strong>Missing GST Accounts:</strong> {0}`, [missing_accounts.join(", ")]),
        "orange",
        true
    );
}

async function fetch_and_update_missing_gst_accounts(frm) {
    const missing_accounts = await get_missing_gst_accounts(frm);
    if (!missing_accounts) return;

    // cleanup existing empty rows
    frm.doc.taxes = frm.doc.taxes.filter(row => row.tax_type);

    // add missing rows
    await Promise.all(
        missing_accounts.map(async account => {
            const tax_rate = await get_tax_rate_for_account(frm, account);
            frm.add_child("taxes", { tax_type: account, tax_rate: tax_rate });
        })
    );

    frm.refresh_field("taxes");
}

async function get_tax_rate_for_account(frm, account) {
    const gst_rate = frm.doc.gst_rate;
    if (!gst_rate) return 0;

    const gst_accounts = await get_gst_accounts(frm);
    if (!gst_accounts) return null;

    const [_, intra_state_accounts, inter_state_accounts] = gst_accounts;

    if (intra_state_accounts.includes(account)) return gst_rate / 2;
    else if (inter_state_accounts.includes(account)) return gst_rate;
    else return null;
}

async function get_missing_gst_accounts(frm) {
    let gst_accounts = await get_gst_accounts(frm);
    if (!gst_accounts) return;

    const all_gst_accounts = gst_accounts[0];
    const template_accounts = frm.doc.taxes.map(t => t.tax_type);
    const missing_accounts = all_gst_accounts.filter(
        a => a && !template_accounts.includes(a)
    );

    if (missing_accounts.length) return missing_accounts;
}

async function get_gst_accounts(frm) {
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
    return frm._company_gst_accounts[company];
}
