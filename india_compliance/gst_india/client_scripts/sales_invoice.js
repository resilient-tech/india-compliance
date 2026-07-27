const DOCTYPE = "Sales Invoice";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });

        frm.set_query("driver", (doc) => {
            return {
                filters: {
                    transporter: doc.transporter,
                },
            };
        });

        frm.set_query("port_address", {
            filters: {
                country: "India",
            },
        });
    },

    before_submit(frm) {
        // desk tag: generate now (on_submit), don't queue it
        frm.doc._submitted_from_ui = 1;
    },

    before_cancel(frm) {
        // desk tag: cancel now (after_cancel), don't queue it
        frm.doc._cancelled_from_ui = 1;
    },

    after_cancel(frm) {
        // auto-cancel: do it now. manual already did it in its dialog -> skip
        if (!should_auto_cancel_e_invoice_e_waybill(frm)) return;

        frappe.show_alert(__("Cancelling e-Invoice / e-Waybill..."));

        frappe
            .xcall("india_compliance.gst_india.utils.e_invoice.cancel_e_invoice_e_waybill_after_commit", {
                docname: frm.doc.name,
            })
            .then(() => frm.reload_doc());
    },

    refresh(frm) {
        set_e_waybill_status_options(frm);
        gst_invoice_warning(frm);

        if (!(gst_settings.enable_e_waybill || gst_settings.enable_e_invoice)) return;
        show_sandbox_mode_indicator();
    },

    async after_save(frm) {
        if (
            frm.doc.customer_address ||
            frm.doc.is_return ||
            frm.doc.is_debit_note ||
            !is_e_waybill_applicable(frm) ||
            !(await has_e_waybill_threshold_met(frm))
        )
            return;

        frappe.show_alert(
            {
                message: __("Billing Address is required to create e-Waybill"),
                indicator: "yellow",
            },
            10,
        );
    },
});

function should_auto_cancel_e_invoice_e_waybill(frm) {
    // settings say auto-cancel this, and still in the cancel window? (like auto_generate_e_waybill)
    if (!india_compliance.is_api_enabled()) return false;

    // IRN cancel also cancels its e-Waybill
    if (frm.doc.irn)
        return (
            india_compliance.is_e_invoice_enabled() &&
            !!gst_settings.auto_cancel_e_invoice &&
            is_irn_cancellable(frm)
        );

    if (frm.doc.ewaybill)
        return (
            gst_settings.enable_e_waybill &&
            !!gst_settings.auto_cancel_e_waybill &&
            is_e_waybill_cancellable(frm)
        );

    return false;
}

async function gst_invoice_warning(frm) {
    const contains_gst_account = frm.doc.taxes.some((row) => row.gst_tax_type);

    if (is_gst_invoice(frm) && !contains_gst_account) {
        frm.dashboard.add_comment(
            __("GST is applicable for this invoice but no tax accounts specified in {0} are charged.", [
                frappe.utils.get_form_link("GST Settings", "GST Settings", true),
            ]),
            "red",
            true,
        );
    }
}

function set_e_waybill_status_options(frm) {
    const options = ["Pending", "Not Applicable"];
    if (!options.includes(frm.doc.e_waybill_status)) {
        options.push(frm.doc.e_waybill_status);
    }
    set_field_options("e_waybill_status", options);
}

function is_gst_invoice(frm) {
    const gst_invoice_conditions =
        !frm.is_dirty() &&
        frm.doc.is_opening != "Yes" &&
        frm.doc.company_gstin &&
        frm.doc.company_gstin != frm.doc.billing_address_gstin &&
        frm.doc.items.some((item) => ["Taxable", "Zero-Rated"].includes(item.gst_treatment));

    if (frm.doc.items[0].gst_treatment === "Zero-Rated")
        return gst_invoice_conditions && frm.doc.is_export_with_gst;
    else return gst_invoice_conditions;
}
