frappe.ui.form.on("Item", {
    onload: function (frm) {
        india_compliance.set_hsn_code_query(frm.get_field("gst_hsn_code"));
    },

    item_group: async function (frm) {
        if (frm.doc.item_group) {
            const { message } = await frappe.db.get_value(
                "Item Group",
                frm.doc.item_group,
                "gst_hsn_code"
            );

            if (message.gst_hsn_code && message.gst_hsn_code !== frm.doc.gst_hsn_code) {
                frm.set_value("gst_hsn_code", message.gst_hsn_code);
            }
        }
    },

    before_save: async function (frm) {
        if (!frm.doc.gst_hsn_code && frm.doc.item_group) {
            const { message } = await frappe.db.get_value(
                "Item Group",
                frm.doc.item_group,
                "gst_hsn_code"
            );

            frm.set_value("gst_hsn_code", message.gst_hsn_code);
        }
    },

    gst_hsn_code: function (frm) {
        if ((!frm.doc.taxes || !frm.doc.taxes.length) && frm.doc.gst_hsn_code) {
            frappe.db.get_doc("GST HSN Code", frm.doc.gst_hsn_code).then(hsn_doc => {
                $.each(hsn_doc.taxes || [], function (_, tax) {
                    let a = frappe.model.add_child(frm.doc, "Item Tax", "taxes");
                    a.item_tax_template = tax.item_tax_template;
                    a.tax_category = tax.tax_category;
                    a.valid_from = tax.valid_from;
                    frm.refresh_field("taxes");
                });
            });
        }
    },
});
