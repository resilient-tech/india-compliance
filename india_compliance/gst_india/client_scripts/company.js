{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Company";

update_gstin_in_other_documents(DOCTYPE);

frappe.ui.form.off(DOCTYPE, "make_default_tax_template");
frappe.ui.form.on(DOCTYPE, {
    make_default_tax_template: function (frm) {
        frappe.call({
            method: "india_compliance.gst_india.override.company.make_default_tax_templates",
            args: {
                company: frm.doc.name,
                country: frm.doc.country,
            },
            callback: function () {
                frappe.msgprint(__("Default Tax Templates created"));
            },
        });
    },
});
