frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.__onload?.e_invoice_info?.is_generated_in_sandbox_mode)
            frm.get_field("irn").set_description("Generated in Sandbox Mode");

        if (
            frm.doc.irn &&
            frm.doc.docstatus === 2 &&
            frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name)
        ) {
            frm.add_custom_button(
                __("Mark as Cancelled"),
                () => show_mark_e_invoice_as_cancelled_dialog(frm),
                "e-Invoice",
            );

            india_compliance.make_text_red("e-Invoice", "Mark as Cancelled");
        }

        if (!india_compliance.is_e_invoice_enabled()) return;

        // portal cancel is open for 24h, invoice cancelled or not
        if (frm.doc.docstatus === 2) {
            if (can_cancel_irn(frm)) {
                india_compliance.show_cancel_headline(frm, __("IRN is still active and cancellable."), () =>
                    show_cancel_e_invoice_dialog(frm),
                );
            }

            add_cancel_e_invoice_button(frm);
            return;
        }

        // the applicability date gates generation only; an existing IRN stays cancellable
        if (is_valid_e_invoice_applicability_date(frm)) add_e_invoice_generation_buttons(frm);

        add_cancel_e_invoice_button(frm);
    },
});

function add_e_invoice_generation_buttons(frm) {
    const is_einv_generatable = is_e_invoice_generatable(frm, true);

    if (frm.doc.docstatus === 0 || !is_einv_generatable) {
        frm.add_custom_button(
            __("Applicability Status"),
            () => show_e_invoice_applicability_status(frm, is_einv_generatable),
            "e-Invoice",
        );

        return;
    }

    if (!frm.doc.irn && frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name)) {
        frm.add_custom_button(
            __("Generate"),
            () => {
                frappe.call({
                    method: "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
                    args: { docname: frm.doc.name, force: true },
                    callback: async (r) => {
                        if (r.message?.error_code == "2283") {
                            await taxpayer_api.call({
                                method: "india_compliance.gst_india.utils.e_invoice.handle_duplicate_irn_error",
                                args: r.message,
                            });
                        }
                        frm.refresh();
                    },
                });
            },
            "e-Invoice",
        );

        frm.add_custom_button(
            __("Mark as Generated"),
            () => show_mark_e_invoice_as_generated_dialog(frm),
            "e-Invoice",
        );
    }
}

function is_irn_cancellable(frm) {
    const e_invoice_info = frm.doc.__onload && frm.doc.__onload.e_invoice_info;
    return (
        e_invoice_info &&
        frappe.datetime.convert_to_user_tz(e_invoice_info.acknowledged_on, false).add("days", 1).diff() > 0
    );
}

<<<<<<< HEAD
function show_cancel_e_invoice_dialog(frm, callback) {
    const d = new frappe.ui.Dialog({
        title: frm.doc.ewaybill ? __("Cancel e-Invoice and e-Waybill") : __("Cancel e-Invoice"),
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
            ${__("Sales invoice will be cancelled along with the IRN.")}
        </div>
    `).prependTo(d.wrapper);
=======
function can_cancel_irn(frm) {
    return (
        frm.doc.irn && is_irn_cancellable(frm) && frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name)
    );
>>>>>>> a24e8c7 (fix: multiple fixes for e-Invoice e-Waybill workflows (#4621))
}

function add_cancel_e_invoice_button(frm) {
    if (!can_cancel_irn(frm)) return;

    frm.add_custom_button(__("Cancel"), () => show_cancel_e_invoice_dialog(frm), "e-Invoice");

    india_compliance.make_text_red("e-Invoice", "Cancel");
}

// true: go ahead with the cancel, false: stop
function confirm_irn_cancellation(frm) {
    if (!is_irn_cancellable(frm) || !india_compliance.is_e_invoice_enabled())
        return india_compliance.warn(__("Cannot Cancel IRN"), get_irn_not_cancellable_message(frm));

    // auto-cancelled after the invoice is cancelled
    if (gst_settings.auto_cancel_e_invoice) return Promise.resolve(true);

    return show_cancel_e_invoice_dialog(frm, { before_doc_cancel: true });
}

function get_irn_not_cancellable_message(frm) {
    let message = "";

    if (frm.doc.is_return)
        message = __(
            `You should ideally create a standalone <strong>Debit Note</strong>
                    against this credit note instead of cancelling it.`,
        );
    else if (frm.doc.is_debit_note)
        message = __(
            `You should ideally create a standalone <strong>Credit Note</strong>
                    against this debit note instead of cancelling it.`,
        );
    else
        message = __(
            `You should ideally create a <strong>Credit Note</strong>
                    against this invoice instead of cancelling it.`,
        );

    return (
        message +
        __(
            `<br><br>If you choose to proceed, you'll be required to manually exclude this
                IRN when filing GST Returns.<br><br>

                Are you sure you want to continue?`,
        )
    );
}

// true: IRN cancelled or skipped, false: backed out
function show_cancel_e_invoice_dialog(frm, { before_doc_cancel = false } = {}) {
    return new Promise((resolve) => {
        const d = new frappe.ui.Dialog({
            title: frm.doc.ewaybill ? __("Cancel e-Invoice and e-Waybill") : __("Cancel e-Invoice"),
            fields: get_cancel_e_invoice_dialog_fields(frm),
            primary_action_label: frm.doc.ewaybill ? __("Cancel IRN, e-Waybill") : __("Cancel IRN"),
            async primary_action(values) {
                const cancelled = await cancel_on_portal(
                    frm,
                    "india_compliance.gst_india.utils.e_invoice.cancel_e_invoice",
                    { docname: frm.doc.name, values },
                    d.get_primary_btn(),
                );

                // failed: keep the dialog open to retry, skip or close
                if (!cancelled) return;

                d.onhide = null;
                d.hide();
                resolve(true);
            },
            onhide: () => resolve(false), // closed without acting
        });

        if (before_doc_cancel) {
            d.set_secondary_action_label(__("Cancel Invoice Only"));
            d.set_secondary_action(() => {
                d.onhide = null;
                d.hide();
                resolve(true);
            });
        }

        india_compliance.primary_to_danger_btn(d);
        d.show();
    });
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
            default: manual_cancel
                ? "Others"
                : gst_settings.reason_for_e_invoice_cancellation || "Data Entry Mistake",
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

    let is_invalid_invoice_number = india_compliance.validate_invoice_number(frm.doc.name);

    if (is_invalid_invoice_number.length > 0) {
        is_einv_applicable = false;
        frm._einv_message_list.push(...is_invalid_invoice_number);
    }

    return is_einv_applicable;
}

function is_e_invoice_applicable(frm, show_message = false) {
    frm._einv_message_list = [];

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
        message_list.push(__("Company GSTIN is not set. Ensure it's set in Company Address."));
    }

    if (frm.doc.company_gstin == frm.doc.billing_address_gstin) {
        is_einv_applicable = false;
        message_list.push(__("Company GSTIN and Billing Address GSTIN cannot be same."));
    }

    if (frm.doc.place_of_supply != "96-Other Countries" && !frm.doc.billing_address_gstin) {
        is_einv_applicable = false;
        message_list.push(__("Billing Address GSTIN is required for B2B categorization"));
    }

    if (
        gst_settings.nil_exempt_e_invoice_treatment === "Do Not Generate" &&
        !frm.doc.items.some((item) => ["Taxable", "Zero-Rated"].includes(item.gst_treatment))
    ) {
        is_einv_applicable = false;
        message_list.push(
            __(
                "All items are either Nil-Rated/Exempted/Non-GST. At least one item must be taxable or the transaction should be categorised as export.",
            ),
        );
    }

    if (show_message) frm._einv_message_list.push(...message_list);

    return is_einv_applicable;
}

function show_e_invoice_applicability_status(frm, is_einv_applicable) {
    if (frm.doc.docstatus == 0 && is_einv_applicable) {
        frm._einv_message_list = [__("Please submit the doc to generate e-Invoice.")];
    }

    frappe.msgprint({
        title: is_einv_applicable ? __("e-Invoice can be generated") : __("e-Invoice cannot be generated"),
        message: frm._einv_message_list,
        as_list: true,
        indicator: is_einv_applicable ? "green" : "red",
    });
}

function is_valid_e_invoice_applicability_date(frm) {
    let e_invoice_applicable_from = gst_settings.e_invoice_applicable_from;

    if (gst_settings.apply_e_invoice_only_for_selected_companies)
        e_invoice_applicable_from = gst_settings.e_invoice_applicable_companies.find(
            (row) => row.company == frm.doc.company,
        )?.applicable_from;

    if (!e_invoice_applicable_from) return false;

    return moment(frm.doc.posting_date).diff(e_invoice_applicable_from) >= 0 ? true : false;
}
