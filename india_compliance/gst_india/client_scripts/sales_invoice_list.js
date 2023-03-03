const DOCTYPE = "Sales Invoice";
const erpnext_onload = frappe.listview_settings[DOCTYPE].onload;
frappe.listview_settings[DOCTYPE].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    if (!frappe.perm.has_perm(DOCTYPE, 0, "submit")) return;

    if (gst_settings.enable_e_waybill)
        add_bulk_action_for_submitted_invoices(
            list_view,
            __("Generate e-Waybill JSON"),
            generate_e_waybill_json
        );

    if (ic.is_e_invoice_enabled())
        add_bulk_action_for_submitted_invoices(
            list_view,
            __("Enqueue Bulk e-Invoice Generation"),
            enqueue_bulk_e_invoice_generation
        );
};

function add_bulk_action_for_submitted_invoices(list_view, label, callback) {
    list_view.page.add_actions_menu_item(label, async () => {
        const selected_docs = list_view.get_checked_items();
        const submitted_docs = await validate_if_submitted(selected_docs);
        if (submitted_docs) callback(submitted_docs);
    });
}

async function generate_e_waybill_json(docnames) {
    const ewb_data = await frappe.xcall(
        "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
        { doctype: DOCTYPE, docnames }
    );

    trigger_file_download(ewb_data, get_e_waybill_file_name());
}

async function enqueue_bulk_e_invoice_generation(docnames) {
    const now = frappe.datetime.system_datetime();

    const job_id = await frappe.xcall(
        "india_compliance.gst_india.utils.e_invoice.enqueue_bulk_e_invoice_generation",
        { docnames }
    );

    const api_requests_link = frappe.utils.generate_route({
        type: "doctype",
        name: "Integration Request",
        route_options: {
            integration_request_service: "India Compliance API",
            creation: `[">", "${now}"]`,
        },
    });

    frappe.msgprint(
        __(
            "Bulk e-Invoice Generation has been queued. You can track the <a href='{0}'>Background Job</a> and <a href='{1}'>API Requests</a>.",
            [frappe.utils.get_form_link("RQ Job", job_id), api_requests_link]
        )
    );
}

async function validate_if_submitted(selected_docs) {
    const valid_docs = [];
    const invalid_docs = [];

    for (const doc of selected_docs) {
        if (doc.docstatus != 1) {
            invalid_docs.push(doc.name);
        } else {
            valid_docs.push(doc.name);
        }
    }

    if (!invalid_docs.length) return valid_docs;

    if (!valid_docs.length) {
        frappe.throw(__("This action can only be performed on submitted documents"));
    }

    const confirmed = await new Promise(resolve => {
        frappe.confirm(
            __(
                "This action can only be performed on submitted documents. Do you want to continue without the following documents?<br><br><strong>{0}</strong>",
                [invalid_docs.join("<br>")]
            ),
            () => resolve(true)
        );
    });

    return confirmed ? valid_docs : false;
}
