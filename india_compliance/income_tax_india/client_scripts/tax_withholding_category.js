frappe.ui.form.on("Tax Withholding Category", {
    refresh: show_missing_tds_section_and_entity_type_banner
});

async function show_missing_tds_section_and_entity_type_banner(frm) {
    const {doc,dashboard}=frm
    if (frm.is_new()===1 || (doc?.tds_section && doc?.entity_type) ) return;
    dashboard.add_comment(
        __(`TDS section and Entity type are not properly set`),
        "red",
        true
    );
}