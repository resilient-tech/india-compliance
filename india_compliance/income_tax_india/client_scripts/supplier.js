// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Supplier", {
    refresh(frm) {
        india_compliance.setup_indian_fiscal_year_options(frm, "india_msme_classification");
    },
});
