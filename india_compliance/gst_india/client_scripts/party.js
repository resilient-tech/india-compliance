function update_old_gstin(doctype) {
    frappe.ui.form.on(doctype, {
        after_save: function (frm) {
            if (!frappe.last_response.docs_with_old_gstin) return;
            let data = frappe.last_response.docs_with_old_gstin;
            let message = "";
            for (const [dt, dns] of Object.entries(data.docs_with_old_gstin)) {
                message += `<br><br><strong>${dt}</strong>:`;
                for (const dn in dns) {
                    message += `<br>${dns[dn]}`;
                }
            }

            frappe.confirm(
                `You are using this old GSTIN <strong>${data.old_gstin}</strong> at following other places. Do you want to update it?${message}`,
                function () {
                    frappe.call({
                        method: "india_compliance.gst_india.overrides.party.update_docs_with_old_gstin",
                        args: {
                            new_gstin: frm.doc.gstin,
                            new_gst_category: frm.doc.gst_category,
                            docs_with_old_gstin: data.docs_with_old_gstin,
                        },
                    });
                }
            );
        },
    });
}
