frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (!is_e_invoice_applicable(frm) || frm.doc.docstatus != 1) return;
        if (frm.doc.e_invoice_status == "Pending" || !frm.doc.irn) {
            frm.add_custom_button(
                "Generate",
                async () => {
                    await frappe.call({
                        method: "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
                        args: {
                            docname: frm.doc.name,
                        },
                        freeze: true,
                    });
                    frm.reload_doc();
                },
                "e-Invoice"
            );
        }
        if (!frm.doc.e_invoice_date) return;
        let dateutil = frappe.datetime;
        const expiry_time = dateutil.get_datetime_as_string(
            dateutil.str_to_obj(frm.doc.e_invoice_date).addHours(24)
        );
        const now_datetime = dateutil.now_datetime();

        if (
            frm.doc.e_invoice_status == "Generated" &&
            frm.doc.irn &&
            expiry_time > now_datetime
        ) {
            frm.add_custom_button(
                "Cancel",
                () => {
                    trigger_file_download(
                        frm.doc.e_invoice_json,
                        get_e_invoice_file_name(frm.doc.name)
                    );
                },
                "e-Invoice"
            );
        }
    },
    validate(frm) {
        if (is_e_invoice_applicable(frm) && !gst_settings.auto_generate_e_invoice)
            frm.set_value("einvoice_status", "Pending");
    },
    on_submit(frm) {
        if (!is_e_invoice_applicable(frm) || !gst_settings.auto_generate_e_invoice)
            return;

        frappe.call({
            method: "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
            args: {
                docname: frm.doc.name,
                throw: false,
            },
            callback: r => frm.reload_doc(),
        });
    },
});

function is_e_invoice_applicable(frm) {
    return !(
        !gst_settings.enable_api ||
        !gst_settings.enable_e_invoice ||
        gst_settings.e_invoice_applicable_from > frm.doc.posting_date ||
        !frm.company_gstin ||
        frm.doc.gst_category == "Unregistered" ||
        frm.doc.items[0].is_non_gst
    );
}

Date.prototype.addHours = function (h) {
    this.setTime(this.getTime() + h * 60 * 60 * 1000);
    return this;
};
