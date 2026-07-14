// Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("GSTR 3B Report", {
    setup: function () {
        frappe.require("assets/india_compliance/js/gstr_2b.js");
    },

    onload: function (frm) {
        set_options_for_year_month(frm);

        if (frm.doc.company && frm.is_new()) {
            india_compliance.set_gstin_options(frm, false, true).then((options) => {
                if (options && options.length) frm.set_value("company_gstin", options[0]);
            });
        }

        frappe.realtime.on("gstr3b_report_generation", function () {
            frm.reload_doc();
        });
    },

    refresh: function (frm) {
        frm.toggle_display("json_output", 0);
        set_primary_action_label(frm);

        if (frm.is_new()) return;

        const is_filed = frm.doc.filing_status === "Filed";
        frm.page.set_indicator(is_filed ? __("Filed") : __("Not Filed"), is_filed ? "green" : "orange");

        // making form dirty without UI changes
        frm.doc.__unsaved = 1;

        append_form(frm);

        // Download Buttons
        const report_method = "india_compliance.gst_india.doctype.gstr_3b_report.gstr_3b_report";
        const docname = encodeURIComponent(frm.doc.name);
        const download_group = __("Download");

        if (frappe.model.can_print(frm.doctype, frm)) {
            frm.add_custom_button(
                __("JSON"),
                () => open_download(`${report_method}.make_json?name=${docname}`),
                download_group,
            );

            frm.add_custom_button(
                __("Excel"),
                () => open_download(`${report_method}.download_gstr3b_as_excel?name=${docname}`),
                download_group,
            );

            frm.add_custom_button(
                __("PDF"),
                () => open_download(`${report_method}.download_gstr3b_as_pdf?name=${docname}`),
                download_group,
            );
        }

        // Regenerate Button
        frm.add_custom_button(__("Regenerate 2B"), function () {
            frappe.show_alert(__("Regenerating GSTR-2B"));

            gstr_2b.regenerate({
                gstin: frm.doc.company_gstin,
                return_period: india_compliance.get_period(frm.doc.month_or_quarter, frm.doc.year),
                doctype: frm.doc.doctype,
                callback: function (regeneration_status) {
                    if (regeneration_status.status === "ER") {
                        frappe.throw(__(regeneration_status.error));
                    } else if (regeneration_status.status === "P") {
                        frappe.show_alert({
                            message: __("Successfully Regenerated GSTR-2B"),
                            indicator: "green",
                        });
                    }
                },
            });
        });

        let action = frm.doc.filing_status === "Filed" ? "Not Filed" : "Filed";
        let status_label = action === "Filed" ? __("Filed") : __("Unfiled");

        frm.add_custom_button(__("Mark as {0}", [status_label]), function () {
            frappe.confirm(
                __("Mark GSTR-3B for {0} {1} as {2}?", [
                    frm.doc.month_or_quarter,
                    frm.doc.year,
                    status_label,
                ]),
                () => {
                    frappe.call({
                        method: "india_compliance.gst_india.utils.itc_claim.update_gstr3b_filing_status",
                        args: {
                            company_gstin: frm.doc.company_gstin,
                            month_or_quarter: frm.doc.month_or_quarter,
                            year: frm.doc.year,
                            status: action,
                        },
                        callback: () => frm.reload_doc(),
                    });
                },
            );
        });
    },

    company: async function (frm) {
        if (!frm.doc.company) {
            frm.set_value("company_gstin", "");
            return;
        }

        const options = await india_compliance.set_gstin_options(frm, false, true);
        frm.set_value("company_gstin", options[0]);
    },
});

function open_download(method) {
    if (!window.open(frappe.urllib.get_full_url(`/api/method/${method}`))) {
        frappe.msgprint(__("Please enable pop-ups"));
    }
}

function set_primary_action_label(frm) {
    const apply = () =>
        frm.page.set_primary_action(frm.is_new() ? __("Generate") : __("Regenerate"), () => frm.save());

    apply();

    // Re-applied on "dirty" because the framework resets it to "Save" on any edit.
    $(frm.wrapper).off("dirty.gstr3b").on("dirty.gstr3b", apply);
}

function append_form(frm) {
    $(frm.fields_dict.gstr3b_form.wrapper).empty();
    $(
        frappe.render_template("gstr_3b_report", {
            data: JSON.parse(frm.doc.json_output),
        }),
    ).appendTo(frm.fields_dict.gstr3b_form.wrapper);
}

function set_options_for_year_month(frm) {
    const { options, current_year } = india_compliance.get_options_for_year("Monthly");
    frm.set_df_property("year", "options", options.slice(0, 3));

    if (!frm.is_new()) return;

    const last_month_name = india_compliance.last_month_name();

    frm.set_value("year", current_year);
    frm.set_value("month_or_quarter", last_month_name);
}
