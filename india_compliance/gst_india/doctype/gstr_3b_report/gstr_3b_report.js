// Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("GSTR 3B Report", {
    setup: function () {
        frappe.require("assets/india_compliance/js/gstr_2b.js");
    },

    onload: function (frm) {
        set_options_for_year_month(frm);

        if (frm.doc.company)
            india_compliance.set_gstin_options(frm).then(options => {
                frm.set_value("company_gstin", options[0]);
            });

        frappe.realtime.on("gstr3b_report_generation", function () {
            frm.reload_doc();
        });
    },

    refresh: function (frm) {
        if (frm.is_new()) return;

        frm.set_intro(__("Please save the report again to rebuild or update"));
        frm.doc.__unsaved = 1;

        // Download Button
        frm.add_custom_button(__("Download JSON"), function () {
            var w = window.open(
                frappe.urllib.get_full_url(
                    "/api/method/india_compliance.gst_india.doctype.gstr_3b_report.gstr_3b_report.make_json?" +
                        "name=" +
                        encodeURIComponent(frm.doc.name)
                )
            );

            if (!w) {
                frappe.msgprint(__("Please enable pop-ups"));
                return;
            }
        });

        // View Form Button
        frm.add_custom_button(__("View Form"), function () {
            frappe.call({
                method: "india_compliance.gst_india.doctype.gstr_3b_report.gstr_3b_report.view_report",
                args: {
                    name: frm.doc.name,
                },
                callback: function (r) {
                    let data = r.message;

                    frappe.ui.get_print_settings(false, print_settings => {
                        frappe.render_grid({
                            template: "gstr_3b_report",
                            title: __(this.doctype),
                            print_settings: print_settings,
                            data: data,
                            columns: [],
                        });
                    });
                },
            });
        });

        append_form(frm);

        // Regenerate Button
        frm.add_custom_button(__("Regenerate 2B"), function () {
            frappe.show_alert(__("Regenerating GSTR-2B"));

            gstr_2b.regenerate({
                gstin: frm.doc.company_gstin,
                return_period: india_compliance.get_period(
                    frm.doc.month_or_quarter,
                    frm.doc.year
                ),
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
    },

    company: async function (frm) {
        if (!frm.doc.company) {
            frm.set_value("company_gstin", "");
            return;
        }

        const options = await india_compliance.set_gstin_options(frm);
        frm.set_value("company_gstin", options[0]);
    },
});

function append_form(frm) {
    if (frm.is_new()) return;

    $(frm.fields_dict.gstr3b_form.wrapper).empty();
    $(
        frappe.render_template("gstr_3b_report", {
            data: JSON.parse(frm.doc.json_output),
        })
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
