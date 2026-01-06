/********
 * Shared Utility Functions for Bulk Actions
 *******/

function add_bulk_action_for_documents(list_view, label, callback, allowed_status) {
    if (!allowed_status) allowed_status = [1];
    list_view.page.add_actions_menu_item(label, async () => {
        const selected_docs = list_view.get_checked_items();
        const submitted_docs = await validate_doc_status(selected_docs, allowed_status);
        if (submitted_docs && submitted_docs.length > 0) {
            callback(submitted_docs);
        }
    });
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
            () => resolve(true),
            () => resolve(false)
        );
    });

    return confirmed ? valid_docs : false;
}
