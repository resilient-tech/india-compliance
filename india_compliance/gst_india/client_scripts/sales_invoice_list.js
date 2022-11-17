const erpnext_onload = frappe.listview_settings["Sales Invoice"].onload;
frappe.listview_settings["Sales Invoice"].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    list_view.page.add_actions_menu_item(__("Generate e-Waybill JSON"), () => {
        bulk_generate(__("e-Waybill JSON"), generate_e_waybill_json);
    }, false);

    list_view.page.add_action_item(__("Bulk Generate e-Invoice"), () => {
        bulk_generate(__("e-Invoice"), generate_e_invoice);
    }, false);


    // utility functions
    function bulk_generate(label, callback) {
        const selected_docs = list_view.get_checked_items();
        const docnames = list_view.get_checked_items(true);

        validate_draft_invoices(selected_docs, label);

        frappe.confirm(__("Bulk generate {0} {1} ?", [selected_docs.length, __(label)]), () => {
            callback(docnames);
        });
    }

    const generate_e_waybill_json = async (docnames) => {
        const ewb_data = await frappe.xcall(
            "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
            { doctype: list_view.doctype, docnames }
        );

        trigger_file_download(ewb_data, get_e_waybill_file_name());
    };

    const generate_e_invoice = async (docnames) => {
        await frappe.xcall(
            "india_compliance.gst_india.overrides.sales_invoice._generate_e_invoice",
            { docnames }
        ).then(() => {
            let route = frappe.utils.generate_route({
                'type': "doctype",
                'doc_view': "List",
                'name': "Integration Request",
            })
            frappe.msgprint(__('Bulk Generation is queued. Check the progress in <a href="{0}">Integration Request</a> Log.', [route]));
        });
    }
};

function validate_draft_invoices(selected_docs, label) {
    const draft_invoices = selected_docs.filter(doc => doc.docstatus == 0);

    if (draft_invoices.length) {
        let message = __("{0} can only be generated from a submitted document. <br/>Please submit the following documents first: <br/>", [__(label)]);

        draft_invoices.forEach((doc_name) => {
            message += `${frappe.utils.get_form_link(
                doctype,
                doc_name.name,
                true
            )}<br/>`;
        });

        frappe.throw(message);
    }
}
