frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (!is_e_invoice_applicable(frm) || frm.doc.docstatus != 1) return;
        if (frm.doc.einvoice_status == "Pending" || !frm.doc.irn) {
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
        let e_invoice_info = frm.doc.__onload.e_invoice_info;
        let dateutil = frappe.datetime;
        const expiry_time = dateutil.get_datetime_as_string(
            dateutil.str_to_obj(e_invoice_info.ack_date).addHours(24)
        );
        const now_datetime = dateutil.now_datetime();
        console.log(expiry_time, now_datetime);
        if (
            frm.doc.einvoice_status == "Generated" &&
            frm.doc.irn &&
            expiry_time > now_datetime
        ) {
            frm.add_custom_button(
                "Cancel",
                () => dialog_cancel_e_invoice(frm),
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
        console.log("calling generate_e_invoice");
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

function dialog_cancel_e_invoice(frm) {
    let d = new frappe.ui.Dialog({
        title: frm.doc.ewaybill
            ? __("Cancel e-Invoice and e-Waybill")
            : __("Cancel e-Invoice"),
        fields: [
            {
                label: "IRN Number",
                fieldname: "irn",
                fieldtype: "Data",
                read_only: 1,
                default: frm.doc.irn,
            },
            {
                label: "e-Waybill Number",
                fieldname: "ewaybill",
                fieldtype: "Data",
                read_only: 1,
                default: frm.doc.ewaybill,
            },
            {
                label: "Reason",
                fieldname: "reason",
                fieldtype: "Select",
                reqd: 1,
                default: "Data Entry Mistake",
                options: [
                    "Duplicate",
                    "Data Entry Mistake",
                    "Order Cancelled",
                    "Others",
                ],
            },
            {
                label: "Remark",
                fieldname: "remark",
                fieldtype: "Data",
                reqd: 1,
                mandatory_depends_on: "eval: doc.reason == 'Others'",
            },
        ],
        primary_action_label: frm.doc.ewaybill
            ? __("Cancel IRN & e-Waybill")
            : __("Cancel IRN"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_invoice.cancel_e_invoice",
                args: {
                    docname: frm.doc.name,
                    values: values,
                },
                callback: function () {
                    frm.reload_doc();
                },
            });
            d.hide();
        },
    });

    d.show();
}

function is_e_invoice_applicable(frm) {
    return (
        gst_settings.enable_api &&
        gst_settings.enable_e_invoice &&
        gst_settings.e_invoice_applicable_from <= frm.doc.posting_date &&
        frm.doc.company_gstin &&
        frm.doc.gst_category != "Unregistered" &&
        !frm.doc.items[0].is_non_gst
    );
}

Date.prototype.addHours = function (h) {
    this.setTime(this.getTime() + h * 60 * 60 * 1000);
    return this;
};
