frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.docstatus != 1 || !is_e_invoice_applicable(frm)) return;
        if (
            !frm.doc.irn &&
            frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name)
        ) {
            frm.add_custom_button(
                __("Generate"),
                async () => {
                    await frappe.call({
                        method: "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
                        args: { docname: frm.doc.name },
                        callback: () => frm.refresh(),
                    });
                },
                "e-Invoice"
            );
        }
        if (
            frm.doc.irn &&
            is_irn_cancellable(frm) &&
            frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name)
        ) {
            frm.add_custom_button(
                __("Cancel"),
                () => show_cancel_e_invoice_dialog(frm),
                "e-Invoice"
            );
        }
    },
    validate(frm) {
        if (is_e_invoice_applicable(frm) && !gst_settings.auto_generate_e_invoice)
            frm.set_value("einvoice_status", "Pending");
    },
    on_submit(frm) {
        if (
            frm.doc.irn ||
            !is_e_invoice_applicable(frm) ||
            !gst_settings.auto_generate_e_invoice
        )
            return;

        frappe.call({
            method: "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
            args: {
                docname: frm.doc.name,
                throw: false,
            },
            callback: () => frm.refresh(),
        });
    },
});

function is_irn_cancellable(frm) {
    const e_invoice_info = frm.doc.__onload && frm.doc.__onload.e_invoice_info;
    return (
        e_invoice_info &&
        frappe.datetime
            .convert_to_user_tz(e_invoice_info.acknowledged_on, false)
            .add("days", 1)
            .diff() > 0
    );
}

function show_cancel_e_invoice_dialog(frm, callback) {
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
                    frm.refresh();
                    callback && callback();
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
