{% include "india_compliance/gst_india/client_scripts/taxes.js" %}
{% include "india_compliance/gst_india/client_scripts/invoice.js" %}

const DOCTYPE = "Sales Invoice";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
setup_e_waybill_actions(DOCTYPE);
update_gst_vehicle_type(DOCTYPE);
validate_overseas_gst_category(DOCTYPE);


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
    }
});
