frappe.ui.form.off("Company", "make_default_tax_template");
frappe.ui.form.on("Company", {
    make_default_tax_template: function (frm) {
        frappe.call({
            method: "india_compliance.gst_india.override.company._make_default_tax_templates",
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
