const erpnext_onload = frappe.listview_settings["Sales Invoice"].onload;
frappe.listview_settings["Sales Invoice"].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    if (!frappe.perm.has_perm("Sales Invoice", 0, "submit") || !ic.is_api_enabled())
        return;
    
    if (gst_settings.enable_e_waybill)
        bulk_generate(list_view, "e-Waybill JSON", generate_e_waybill_json);
    
    if (gst_settings.enable_e_invoice)
        bulk_generate(list_view, "e-Invoice", generate_e_invoice);
};

// utility functions
function bulk_generate(list_view, label, callback) {
    list_view.page.add_actions_menu_item(
        __("Generate {0}", [__(label)]),
        () => {
            const selected_docs = list_view.get_checked_items();
            const docnames = list_view.get_checked_items(true);
            validate_draft_invoices(selected_docs, label);
            callback(docnames);
        },
        false
    );
}

async function generate_e_waybill_json(docnames) {
    const ewb_data = await frappe.xcall(
        "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
        { doctype: list_view.doctype, docnames }
    );

    trigger_file_download(ewb_data, get_e_waybill_file_name());
}

function generate_e_invoice(docnames) {
    frappe.xcall(
        "india_compliance.gst_india.overrides.sales_invoice.generate_e_invoice",
        { docnames }
    );
    
    const today = frappe.datetime.get_today();
    const route = frappe.utils.generate_route({
        type: "doctype",
        name: "Integration Request",
        route_options: {
            integration_request_service: "India Compliance API",
            creation: `["Between",["${today}", "${today}"]]`,
        },
    });
    frappe.msgprint(
        __(
            'Bulk Generation is queued. Check the progress in <a href="{0}">Integration Request</a> Log.',
            [route]
        )
    );
}

function validate_draft_invoices(selected_docs, label) {
    const draft_invoices = selected_docs.filter(doc => doc.docstatus == 0);
    if (!draft_invoices.length) return;

    frappe.throw(
        __("{0} can only be generated from a submitted document.", [__(label)])
    );
}
