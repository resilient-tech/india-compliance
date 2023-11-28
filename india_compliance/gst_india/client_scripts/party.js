const TCS_REGEX = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[C]{1}[0-9A-Z]{1}$/;
const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;

function update_gstin_in_other_documents(doctype) {
    frappe.ui.form.on(doctype, {
        after_save(frm) {
            // docs to be updated attached to previous response
            const { docs_with_previous_gstin, previous_gstin } = frappe.last_response;
            if (!docs_with_previous_gstin) return;

            const { gstin, gst_category } = frm.doc;
            let message = __(
                "You were using the GSTIN <strong>{0}</strong> in the following other documents:<br>",
                [previous_gstin]
            );

            for (const [doctype, docnames] of Object.entries(
                docs_with_previous_gstin
            )) {
                message += `<br><strong>${__(doctype)}</strong>:<br>`;

                docnames.forEach(docname => {
                    message += `${frappe.utils.get_form_link(
                        doctype,
                        docname,
                        true
                    )}<br>`;
                });
            }
            message += `<br>Do you want to update these with the following new values?
                        <br>
                        <br><strong>GSTIN:</strong> ${gstin || "&lt;empty&gt;"}
                        <br><strong>GST Category:</strong> ${gst_category}`;

            frappe.confirm(message, function () {
                frappe.call({
                    method: "india_compliance.gst_india.overrides.party.update_docs_with_previous_gstin",
                    args: {
                        gstin: gstin || "",
                        gst_category,
                        docs_with_previous_gstin,
                    },
                });
            });
        },
    });
}

function validate_gstin(doctype) {
    frappe.ui.form.on(doctype, {
        gstin(frm) {
            let { gstin } = frm.doc;

            // TODO: remove below condition once event is fixed in frappe
            if (!gstin || gstin.length < 15) return;

            if (gstin.length > 15) {
                frappe.throw(__("GSTIN/UIN should be 15 characters long"));
            }

            gstin = india_compliance.validate_gstin(gstin);

            if (TCS_REGEX.test(gstin)) {
                frappe.throw(__("e-Commerce Operator (TCS) GSTIN is not allowed to be set in Party/Address"));
            }

            frm.doc.gstin = gstin;
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

function show_overseas_disabled_warning(doctype) {
    frappe.ui.form.on(doctype, {
        after_save(frm) {
            if (
                !gst_settings.enable_overseas_transactions &&
                in_list(["SEZ", "Overseas"], frm.doc.gst_category)
            ) {
                frappe.msgprint({
                    message: __(
                        `SEZ/Overseas transactions are disabled in GST Settings.
                        Please enable this setting to create transactions for this party.`
                    ),
                    indicator: "orange",
                });
            }
        },
    });
}

function set_gstin_options_and_status(doctype) {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            set_gstin_options(frm);
            india_compliance.set_gstin_status(frm.get_field("gstin"));
        },
        gstin(frm) {
            india_compliance.set_gstin_status(frm.get_field("gstin"));
        },
    });
}

async function set_gstin_options(frm) {
    if (frm.is_new() || frm._gstin_options_set_for === frm.doc.name) return;

    frm._gstin_options_set_for = frm.doc.name;
    const field = frm.get_field("gstin");
    field.df.ignore_validation = true;
    field.set_data(await india_compliance.get_gstin_options(frm.doc.name, frm.doctype));
}

function set_gst_category(doctype) {
    frappe.ui.form.on(doctype, {
        gstin(frm) {
            frm.set_value(
                "gst_category",
                india_compliance.guess_gst_category(frm.doc.gstin, frm.doc.country)
            );
        },
    });
}
