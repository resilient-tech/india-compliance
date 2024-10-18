frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.__onload?.e_invoice_info?.is_generated_in_sandbox_mode)
            frm.get_field("irn").set_description("Generated in Sandbox Mode");

        if (
            frm.doc.irn &&
            frm.doc.docstatus == 2 &&
            frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name)
        ) {
            frm.add_custom_button(
                __("Mark as Cancelled"),
                () => show_mark_e_invoice_as_cancelled_dialog(frm),
                "e-Invoice"
            );
        }

        if (
            !india_compliance.is_e_invoice_enabled() ||
            !is_valid_e_invoice_applicability_date(frm)
        )
            return;

        if(frm.doc.docstatus === 2) return;

        const is_einv_generatable = is_e_invoice_generatable(frm, true);

        if (frm.doc.docstatus === 0 || !is_einv_generatable) {
            frm.add_custom_button(
                __("Applicability Status"),
                () =>
                    show_e_invoice_applicability_status(
                        frm,
                        is_einv_generatable
                    ),
                "e-Invoice"
            );

            return;
        }

        if (
            !frm.doc.irn &&
            frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name)
        ) {
            frm.add_custom_button(
                __("Generate"),
                () => {
                    frappe.call({
                        method: "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
                        args: { docname: frm.doc.name, force: true },
                        callback: async (r) => {
                            if (r.message?.error_type == "otp_requested") {
                                await india_compliance.authenticate_otp(frm.doc.company_gstin);
                                await frappe.call({
                                    method: "india_compliance.gst_india.utils.e_invoice.handle_duplicate_irn_error",
                                    args: r.message
                                });
                            }
                            frm.refresh();
                        },
                    });
                },
                "e-Invoice"
            );

            frm.add_custom_button(
                __("Mark as Generated"),
                () => show_mark_e_invoice_as_generated_dialog(frm),
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

            india_compliance.make_text_red("e-Invoice", "Cancel");
        }
    },
    async on_submit(frm) {
        if (
            frm.doc.irn ||
            !is_e_invoice_applicable(frm) ||
            !gst_settings.auto_generate_e_invoice
        )
            return;

        frappe.show_alert(__("Attempting to generate e-Invoice"));

        await frappe.xcall(
            "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
            {
                docname: frm.doc.name,
                throw: false,
            }
        );
    },
    before_cancel(frm) {
        if (!frm.doc.irn) return;

        frappe.validated = false;

        return new Promise(resolve => {
            const continueCancellation = () => {
                frappe.validated = true;
                resolve();
            };

            if (!is_irn_cancellable(frm) || !india_compliance.is_e_invoice_enabled()) {
                let message = "";

                if (frm.doc.is_return)
                    message = __(
                        `You should ideally create a standalone <strong>Debit Note</strong>
                        against this credit note instead of cancelling it.`
                    );
                else if (frm.doc.is_debit_note)
                    message = __(
                        `You should ideally create a standalone <strong>Credit Note</strong>
                        against this debit note instead of cancelling it.`
                    );
                else
                    message = __(
                        `You should ideally create a <strong>Credit Note</strong>
                    against this invoice instead of cancelling it.`
                    );

                message += __(
                    `<br><br>If you choose to proceed, you'll be required to manually exclude this
                    IRN when filing GST Returns.<br><br>

                    Are you sure you want to continue?`
                );
                const d = frappe.warn(__("Cannot Cancel IRN"), message, continueCancellation, __("Yes"));

                d.set_secondary_action_label(__("No"));
                return;
            }

            return show_cancel_e_invoice_dialog(frm, continueCancellation);
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
    const d = new frappe.ui.Dialog({
        title: frm.doc.ewaybill
            ? __("Cancel e-Invoice and e-Waybill")
            : __("Cancel e-Invoice"),
        fields: get_cancel_e_invoice_dialog_fields(frm),
        primary_action_label: frm.doc.ewaybill
            ? __("Cancel IRN, e-Waybill & Invoice")
            : __("Cancel IRN & Invoice"),
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

    india_compliance.primary_to_danger_btn(d);
    d.show();

    $(`
        <div class="alert alert-warning" role="alert">
            Sales invoice will be cancelled along with the IRN.
        </div>
    `).prependTo(d.wrapper);
}

function show_mark_e_invoice_as_generated_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Update e-Invoice Details"),
        fields: get_generated_e_invoice_dialog_fields(),
        primary_action_label: __("Update"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_invoice.mark_e_invoice_as_generated",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    values,
                },
                callback: () => {
                    d.hide();
                    frm.refresh();
                },
            });
        },
    });

    d.show();
}

function get_generated_e_invoice_dialog_fields() {
    let fields = [
        {
            label: "IRN Number",
            fieldname: "irn",
            fieldtype: "Data",
            reqd: 1,
        },
        {
            label: "Acknowledgement Number",
            fieldname: "ack_no",
            fieldtype: "Data",
            reqd: 1,
        },
        {
            label: "Acknowledged On",
            fieldname: "ack_dt",
            fieldtype: "Datetime",
            reqd: 1,
        },
    ];
    return fields;
}

function show_mark_e_invoice_as_cancelled_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Update Cancelled e-Invoice Details"),
        fields: get_cancel_e_invoice_dialog_fields(frm, true),
        primary_action_label: __("Update"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_invoice.mark_e_invoice_as_cancelled",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    values,
                },
                callback: () => {
                    d.hide();
                    frm.refresh();
                },
            });
        },
    });

    d.show();
}

function get_cancel_e_invoice_dialog_fields(frm, manual_cancel = false) {
    let fields = [
        {
            label: "IRN Number",
            fieldname: "irn",
            fieldtype: "Data",
            read_only: 1,
            default: frm.doc.irn,
        },
        {
            label: "Reason",
            fieldname: "reason",
            fieldtype: "Select",
            reqd: 1,
            default: manual_cancel ? "Others" : "Data Entry Mistake",
            options: ["Duplicate", "Data Entry Mistake", "Order Cancelled", "Others"],
        },
        {
            label: "Remark",
            fieldname: "remark",
            fieldtype: "Data",
            reqd: 1,
            mandatory_depends_on: "eval: doc.reason == 'Others'",
            default: manual_cancel ? "Manually deleted from GSTR-1" : "",
        },
    ];

    if (manual_cancel) {
        fields.push({
            label: "Cancelled On",
            fieldname: "cancelled_on",
            fieldtype: "Datetime",
            reqd: 1,
            default: frappe.datetime.now_datetime(),
        });
    } else {
        fields.splice(1, 0, {
            label: "e-Waybill Number",
            fieldname: "ewaybill",
            fieldtype: "Data",
            read_only: 1,
            default: frm.doc.ewaybill || "",
        });
    }

    return fields;
}

function is_e_invoice_generatable(frm, show_message = false) {
    let is_einv_applicable = is_e_invoice_applicable(frm, show_message);
    if (!show_message) return is_einv_applicable;

    let is_invalid_invoice_number = india_compliance.validate_invoice_number(
        frm.doc.name
    );

    if (is_invalid_invoice_number.length > 0) {
        is_einv_applicable = false;
        frm._einv_message += is_invalid_invoice_number
            .map(message => `<li>${__(message)}</li>`)
            .join("");
    }

    return is_einv_applicable;
}

function is_e_invoice_applicable(frm, show_message = false) {
    if (
        !india_compliance.is_e_invoice_enabled() ||
        (!show_message && frm.doc.docstatus != 1) ||
        !is_valid_e_invoice_applicability_date(frm)
    )
        return false;

    let is_einv_applicable = true;
    let message_list = [];

    if (!frm.doc.company_gstin) {
        is_einv_applicable = false;
        message_list.push(
            "Company GSTIN is not set. Ensure its set in Company Address."
        );
    }

    if (frm.doc.company_gstin == frm.doc.billing_address_gstin) {
        is_einv_applicable = false;
        message_list.push("Company GSTIN and Billing Address GSTIN cannot be same.");
    }

    if (
        frm.doc.place_of_supply != "96-Other Countries" &&
        !frm.doc.billing_address_gstin
    ) {
        is_einv_applicable = false;
        message_list.push("Billing Address GSTIN is required for B2B categorization");
    }

    if (
        !frm.doc.items.some(item =>
            ["Taxable", "Zero-Rated"].includes(item.gst_treatment)
        )
    ) {
        is_einv_applicable = false;
        message_list.push(
            "All items are either Nil-Rated/Exempted/Non-GST. At least one item must be taxable or the transaction should be categorised as export."
        );
    }

    frm._einv_message = "";
    if (show_message)
        frm._einv_message = message_list
            .map(message => `<li>${__(message)}</li>`)
            .join("");

    return is_einv_applicable;
}

function show_e_invoice_applicability_status(frm, is_einv_applicable) {
    if (frm.doc.docstatus == 0 && is_einv_applicable) {
        frm._einv_message = __("Please submit the doc to generate e-Invoice.");
    }

    frappe.msgprint({
        title: is_einv_applicable ? __("e-Invoice can be generated") : __("e-Invoice cannot be generated"),
        message: frm._einv_message,
        indicator: is_einv_applicable ? "green" : "red",
    });
}

function is_valid_e_invoice_applicability_date(frm) {
    let e_invoice_applicable_from = gst_settings.e_invoice_applicable_from;

    if (gst_settings.apply_e_invoice_only_for_selected_companies)
        e_invoice_applicable_from = gst_settings.e_invoice_applicable_companies.find(
            row => row.company == frm.doc.company
        )?.applicable_from;

    if (!e_invoice_applicable_from) return false;

    return moment(frm.doc.posting_date).diff(e_invoice_applicable_from) >= 0
        ? true
        : false;
}
