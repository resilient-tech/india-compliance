function update_gstin_in_other_documents(doctype) {
    frappe.ui.form.on(doctype, {
        after_save(frm) {
            // docs to be updated attached to previous response (validate)
            const { docs_with_previous_gstin, previous_gstin } = frappe.last_response;
            if (!docs_with_previous_gstin) return;

            const { gstin, gst_category } = frm.doc;
            let message = __(
                "You were using the GSTIN <strong>{0}</strong> in following other documents. Do you want to update these?",
                [previous_gstin]
            );
            for (const [doctype, docnames] of Object.entries(
                docs_with_previous_gstin
            )) {
                message += `<br/><br/><strong>${__(doctype)}</strong>:<br/>`;
                message += docnames.join("<br/>");
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
