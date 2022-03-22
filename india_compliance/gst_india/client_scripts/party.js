function update_previous_gstin(doctype) {
    frappe.ui.form.on(doctype, {
        after_save(frm) {
            // docs to be updated attached to previous response (validate)
            const { docs_with_previous_gstin, previous_gstin } =
                frappe.last_response;
            if (!docs_with_previous_gstin) return;

            const { gstin, gst_category } = frm.doc;
            let message = `You are using the GSTIN <strong>${previous_gstin}</strong> at following other places. Do you want to update it?`;
            for (const [doctype, docname_list] of Object.entries(
                docs_with_previous_gstin
            )) {
                message += `<br/><br/><strong>${doctype}</strong>:<br/>`;
                message += docname_list.join("<br/>");
            }

            frappe.confirm(message, function () {
                frappe.call({
                    method: "india_compliance.gst_india.overrides.party.update_docs_with_previous_gstin",
                    args: { gstin, gst_category, docs_with_previous_gstin },
                });
            });
        },
    });
}
