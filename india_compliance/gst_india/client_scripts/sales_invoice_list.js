const erpnext_onload = frappe.listview_settings["Sales Invoice"].onload;
frappe.listview_settings["Sales Invoice"].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    const action = async () => {
        const selected_docs = list_view.get_checked_items();
        const docnames = list_view.get_checked_items(true);

        for (let doc of selected_docs) {
            if (doc.docstatus !== 1) {
                frappe.throw(
                    __("e-Waybill JSON can only be generated from a submitted document")
                );
            }
        }

        const ewb_data = await frappe.xcall(
            "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
            { doctype: list_view.doctype, docnames }
        );

        trigger_file_download(ewb_data, get_e_waybill_file_name());
    };

    list_view.page.add_actions_menu_item(__("Generate e-Waybill JSON"), action, false);

};
