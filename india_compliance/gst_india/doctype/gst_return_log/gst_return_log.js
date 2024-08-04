// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("GST Return Log", {
    refresh(frm) {
        const [month_or_quarter, year] = india_compliance.get_month_year_from_period(
            frm.doc.return_period
        );

        frm.add_custom_button(__("View GSTR-1"), () => {
            frappe.set_route("Form", "GSTR-1 Beta");

            // after form loads
            new Promise(resolve => {
                const interval = setInterval(() => {
                    if (cur_frm.doctype === "GSTR-1 Beta" && cur_frm.__setup_complete) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 100);
            }).then(async () => {
                await cur_frm.set_value({
                    company: frm.doc.company,
                    company_gstin: frm.doc.gstin,
                    year: year,
                    month_or_quarter: month_or_quarter,
                });
                cur_frm.save();
            });
        });
    },
});
