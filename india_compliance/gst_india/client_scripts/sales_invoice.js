{% include "india_compliance/gst_india/client_scripts/taxes.js" %}
{% include "india_compliance/gst_india/client_scripts/invoice.js" %}

const DOCTYPE = "Sales Invoice";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
update_export_type(DOCTYPE);
setup_e_waybill_actions(DOCTYPE);
update_gst_vehicle_type(DOCTYPE);


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
            frm.doc.docstatus != 1 ||
            frm.is_dirty() ||
            frm.doc.ewaybill ||
            frm.doc.is_return ||
            !is_e_waybill_applicable(frm)
        )
            return;

        // ewaybill is applicable and not created or updated.
        frm.dashboard.add_comment(
            "e-Waybill is applicable for this invoice and not yet generated or updated.",
            "yellow",
            true
        );
    }
});
