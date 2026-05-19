frappe.ui.form.on("Tax Withholding Category", {
    setup(frm) {
        frm.set_query("tds_section", () => ({
            query: "india_compliance.income_tax_india.overrides.tax_withholding_category.search_tds_sections",
        }));
    },
});
