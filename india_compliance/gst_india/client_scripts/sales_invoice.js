{% include "india_compliance/gst_india/client_scripts/taxes.js" %}
{% include "india_compliance/gst_india/client_scripts/invoice.js" %}

const DOCTYPE = "Sales Invoice";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
update_export_type(DOCTYPE);
setup_e_waybill_actions(DOCTYPE);

const gst_settings = frappe.boot.gst_settings;

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });

        frm.set_query("driver", doc => {
            return {
                filters: {
                    transporter: doc.transporter,
                },
            };
        });
    },

    async refresh(frm) {
        if (
            gst_settings.enable_api &&
            frm.doc.ewaybill &&
            frm.doc.ewaybill.length == 12
        ) {
            frm.set_df_property("ewaybill", "allow_on_submit", 0);
        }

        if (
            frm.doc.docstatus != 1 ||
            frm.is_dirty() ||
            frm.doc.ewaybill ||
            !gst_settings.enable_e_waybill ||
            !is_e_waybill_applicable(frm)
        )
            return;

        if (!frm.doc.is_return) {
            // ewaybill is applicable and not created or updated.
            frm.dashboard.add_comment(
                "e-Waybill is applicable for this invoice and not yet generated or updated.",
                "yellow"
            );
        }

        if (gst_settings.enable_api) return;

        frm.add_custom_button(
            "e-Waybill JSON",
            async () => {
                const ewb_data = await frappe.xcall(
                    "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
                    { doctype: frm.doctype, docnames: frm.doc.name }
                );

                trigger_file_download(ewb_data, get_e_waybill_file_name(frm.doc.name));
            },
            __("Create")
        );
    },
    before_cancel(frm) {
        if (!gst_settings.enable_api || (!frm.doc.ewaybill && !frm.doc.irn)) return;

        frappe.validated = false;

        return new Promise((resolve) => {
            const continueCancellation = () => {
                frappe.validated = true;
                resolve();
            }

            if (frm.doc.irn) {
				if (!is_irn_cancellable(frm)) {
					return frappe.warn(
						__("IRN cannot be cancelled"),
						__(
                            `A <strong>Credit Note</strong> should ideally be created
                            against this invoice instead of cancelling it. If you
                            choose to proceed, you'll need to update the IRN in the
                            e-Invoice portal manually.`
                        ),
						continueCancellation,
						"Cancel Invoice",
						true
					);
				}

                return show_cancel_e_invoice_dialog(frm, continueCancellation);
			}

            if (!is_e_waybill_cancellable(frm)) {
                return frappe.warn(
                    __("e-Waybill cannot be cancelled"),
                    __(
                        `A <strong>Credit Note</strong> should ideally be created
                        against this invoice instead of cancelling it`
                    ),
                    continueCancellation,
                    "Cancel Invoice",
                    true
                );
            }

            return show_cancel_e_waybill_dialog(frm, continueCancellation);
        });
    },
});
