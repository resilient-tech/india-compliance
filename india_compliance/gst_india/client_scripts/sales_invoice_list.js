const DOCTYPE = "Sales Invoice";

const erpnext_onload = frappe.listview_settings[DOCTYPE].onload;
frappe.listview_settings[DOCTYPE].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    if (!frappe.perm.has_perm(DOCTYPE, 0, "submit")) return;

    if (gst_settings.enable_e_waybill) {
        add_bulk_action_for_invoices(
            list_view,
            __("Generate e-Waybill JSON"),
            generate_e_waybill_json
        );

        add_bulk_action_for_invoices(
            list_view,
            __("Bulk Update Transporter Detail"),
            show_bulk_update_transporter_dialog,
            [0, 1]
        );

        add_bulk_action_for_invoices(
            list_view,
            __("Enqueue Bulk e-Waybill Generation"),
            enqueue_bulk_e_waybill_generation
        );
    }

    if (frappe.model.can_print("e-Waybill Log")) {
        add_bulk_action_for_invoices(
            list_view,
            __("Print e-Waybill"),
            bulk_e_waybill_print
        );
    }

    if (india_compliance.is_e_invoice_enabled())
        add_bulk_action_for_invoices(
            list_view,
            __("Enqueue Bulk e-Invoice Generation"),
            enqueue_bulk_e_invoice_generation
        );
};

function add_bulk_action_for_invoices(list_view, label, callback, allowed_status) {
    if (!allowed_status) allowed_status = [1];
    list_view.page.add_actions_menu_item(label, async () => {
        const selected_docs = list_view.get_checked_items();
        const submitted_docs = await validate_doc_status(selected_docs, allowed_status);
        if (submitted_docs) callback(submitted_docs);
    });
}

async function generate_e_waybill_json(docnames) {
    const ewb_data = await frappe.xcall(
        "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
        { doctype: DOCTYPE, docnames }
    );

    india_compliance.trigger_file_download(ewb_data, get_e_waybill_file_name());
}

function show_bulk_update_transporter_dialog(docnames) {
    const d = get_generate_e_waybill_dialog({
        title: __("Update Transporter Detail"),
        primary_action_label: __("Update Invoices"),
        primary_action(values) {
            d.hide();

            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.bulk_update_transporter_in_docs",
                args: {
                    doctype: DOCTYPE,
                    docnames,
                    values,
                },
            });
        },
    });

    d.show();
}

async function bulk_e_waybill_print(docnames) {
    frappe.call({
        method: "india_compliance.gst_india.utils.e_waybill.get_valid_and_invalid_e_waybill_log",
        args: {
            doctype: DOCTYPE,
            docs: JSON.stringify(docnames),
        },
        callback: function (r) {
            if (r.message) {
                if (r.message.invalid_log.length > 1) {
                    const invalid_docs = r.message.invalid_log.map(
                        doc => `${doc.link} - ${doc.reason}`
                    );
                    frappe.msgprint(
                        __(
                            "Cannot print e-Waybill for following documents:<br><br>{0}",
                            [invalid_docs.join("<br>")]
                        )
                    );
                }

                window.open_url_post(
                    "/api/method/frappe.utils.print_format.download_multi_pdf",
                    {
                        doctype: "e-Waybill Log",
                        name: JSON.stringify(r.message.valid_log),
                    },
                    true
                );
            }
        },
    });
}

async function enqueue_bulk_e_waybill_generation(docnames) {
    enqueue_bulk_generation(
        "india_compliance.gst_india.utils.e_waybill.enqueue_bulk_e_waybill_generation",
        { doctype: DOCTYPE, docnames }
    );
}

async function enqueue_bulk_e_invoice_generation(docnames) {
    enqueue_bulk_generation(
        "india_compliance.gst_india.utils.e_invoice.enqueue_bulk_e_invoice_generation",
        { docnames }
    );
}

async function enqueue_bulk_generation(method, args) {
    const job_id = await frappe.xcall(method, args);

    const now = frappe.datetime.system_datetime();
    const creation_filter = `[">", "${now}"]`;
    const api_requests_link = frappe.utils.generate_route({
        type: "doctype",
        name: "Integration Request",
        route_options: {
            integration_request_service: "India Compliance API",
            creation: creation_filter,
        },
    });
    const error_logs_link = frappe.utils.generate_route({
        type: "doctype",
        name: "Error Log",
        route_options: {
            creation: creation_filter,
        },
    });

    frappe.msgprint(
        __(
            `Bulk Generation has been queued. You can track the
            <a href='{0}'>Background Job</a>,
            <a href='{1}'>API Request(s)</a>,
            and <a href='{2}'>Error Log(s)</a>.`,
            [
                frappe.utils.get_form_link("RQ Job", job_id),
                api_requests_link,
                error_logs_link,
            ]
        )
    );
}

async function validate_doc_status(selected_docs, allowed_status) {
    const valid_docs = [];
    const invalid_docs = [];
    const status_map = {
        0: "draft",
        1: "submitted",
        2: "cancelled",
    };

    for (const doc of selected_docs) {
        if (!allowed_status.includes(doc.docstatus)) {
            invalid_docs.push(doc.name);
        } else {
            valid_docs.push(doc.name);
        }
    }

    if (!invalid_docs.length) return valid_docs;

    const allowed_status_str = allowed_status
        .map(status => status_map[status])
        .join(" or ");

    if (!valid_docs.length) {
        frappe.throw(
            __("This action can only be performed on {0} documents", [
                allowed_status_str,
            ])
        );
    }

    const confirmed = await new Promise(resolve => {
        frappe.confirm(
            __(
                "This action can only be performed on {0} documents. Do you want to continue without the following documents?<br><br><strong>{1}</strong>",
                [allowed_status_str, invalid_docs.join("<br>")]
            ),
            () => resolve(true)
        );
    });

    return confirmed ? valid_docs : false;
}
