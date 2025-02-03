// Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("GSTR 3B Report", {
    onload: function (frm) {
        set_options_for_year_gstr3b(frm);

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

function set_options_for_year_gstr3b(frm) {
    let current_year = new Date().getFullYear();
    let options = [current_year, current_year - 1, current_year - 2];

    frm.set_df_property("year", "options", options);

    if (!frm.is_new()) return;
    frm.set_value("year", options[0]);
}
