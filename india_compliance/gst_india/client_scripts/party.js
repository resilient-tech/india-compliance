function update_invalid_gstin(doctype) {
    frappe.ui.form.on(doctype, {
        after_save: function (frm) {
            if (!frappe.last_response.docs_with_invalid_gstin) return;
            let data = frappe.last_response.docs_with_invalid_gstin;
            let message = `You are using this old GSTIN <strong>${data.invalid_gstin}</strong> at following other places. Do you want to update it?`;
            for (const [doctype, docname_list] of Object.entries(
                data.docs_with_invalid_gstin
            )) {
                message += `<br><br><strong>${doctype}</strong>:`;
                for (const dn in docname_list) {
                    message += `<br>${docname_list[dn]}`;
                }
            }

            frappe.confirm(message, function () {
                frappe.call({
                    method: "india_compliance.gst_india.overrides.party.update_docs_with_invalid_gstin",
                    args: {
                        valid_gstin: frm.doc.gstin,
                        gst_category: frm.doc.gst_category,
                        docs_with_invalid_gstin: data.docs_with_invalid_gstin,
                    },
                });
            });
        },
    });
}
