const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;

function update_gstin_in_other_documents(doctype) {
    frappe.ui.form.on(doctype, {
        after_save(frm) {
            // docs to be updated attached to previous response
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

function validate_gstin(doctype) {
    frappe.ui.form.on(doctype, {
        gstin(frm) {
            const { gstin } = frm.doc;

            // TODO: remove below condition once event is fixed in frappe
            if (!gstin || gstin.length < 15) return;

            if (gstin.length > 15) {
                frappe.throw(__("GSTIN/UIN should be 15 characters long"));
            }

            frm.doc.gstin = gstin.trim().toUpperCase();
            frm.refresh_field("gstin");

            if (!frm.fields_dict.pan) return;

            // extract PAN from GSTIN
            const pan = frm.doc.gstin.slice(2, 12);

            if (PAN_REGEX.test(pan)) {
                frm.doc.pan = pan;
                frm.refresh_field("pan");
            }
        },
    });
}

function validate_pan(doctype) {
    frappe.ui.form.on(doctype, {
        pan(frm) {
            let { pan } = frm.doc;
            if (!pan || pan.length < 10) return;

            if (pan.length > 10) {
                frappe.throw(__("PAN should be 10 characters long"));
            }

            pan = pan.trim().toUpperCase();

            if (!PAN_REGEX.test(pan)) {
                frappe.throw(__("Invalid PAN format"));
            }

            frm.doc.pan = pan;
            frm.refresh_field("pan");
        },
    });
}

function alert_for_disabled_overseas_settings(doctype) {
    frappe.ui.form.on(doctype, {
        validate(frm) {
            if (
                in_list(["SEZ", "Overseas"], frm.doc.gst_category) &&
                !frappe.boot.gst_settings.enable_overseas_transactions
            ) {
                frappe.show_alert({
                    message: __(
                        "SEZ/Overseas transactions are disabled in GST Settings."
                    ),
                    indicator: "orange",
                });
            }
        },
    });
}
