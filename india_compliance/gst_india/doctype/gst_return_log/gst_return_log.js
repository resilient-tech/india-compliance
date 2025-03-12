// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("GST Return Log", {
    onload(frm) {
        const attachFields = [
            "unfiled",
            "unfiled_summary",
            "filed",
            "filed_summary",
            "upload_error",
            "authenticated_summary",
            "books",
            "books_summary",
            "reconcile",
            "reconcile_summary",
        ];

        attachFields.forEach(field => {
            $(frm.fields_dict[field].wrapper).on(
                "click",
                ".control-value a",
                function (e) {
                    e.preventDefault();

                    const args = {
                        cmd: "india_compliance.gst_india.doctype.gst_return_log.gst_return_log.download_file",
                        file_field: field,
                        name: frm.doc.name,
                        doctype: frm.doc.doctype,
                        file_name: `${field}.json.gz`,
                    };
                    open_url_post(frappe.request.url, args);
                }
            );
        });
    },
    refresh(frm) {
        const [month_or_quarter, year] = india_compliance.get_month_year_from_period(
            frm.doc.return_period
        );

        if (frm.doc.return_type !== "GSTR1") return;

        frm.add_custom_button(__("View GSTR-1"), () => {
            frappe.set_route("Form", "GSTR-1 Beta");

            // after form loads
            new Promise(resolve => {
                const interval = setInterval(() => {
                    if (cur_frm.doctype === "GSTR-1 Beta" && cur_frm.__setup_complete) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 200);
            }).then(async () => {
                await cur_frm.set_value({
                    company: frm.doc.company,
                    company_gstin: frm.doc.gstin,
                    year: year,
                    month_or_quarter: month_or_quarter,
                    filing_preference: frm.doc.filing_preference,
                });
                cur_frm.save();
            });
        });
    },
});
