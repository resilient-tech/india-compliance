{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Supplier";

validate_pan(DOCTYPE);
validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
show_overseas_disabled_warning(DOCTYPE);
set_gstin_options_and_status(DOCTYPE);
set_gst_category(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    gstin(frm) {
        if (
            !frm.doc.is_transporter ||
            !frm.doc.gstin ||
            frm.doc.gstin.length < 15 ||
            frm.doc.gst_transporter_id
        )
            return;

        frm.set_value("gst_transporter_id", frm.doc.gstin);
    },

    gst_transporter_id(frm) {
        if (
            !frm.doc.gst_transporter_id ||
            frm.doc.gst_transporter_id.length < 15
        )
            return;

        gst_transporter_id_field = frm.get_field("gst_transporter_id");
        india_compliance.set_gstin_status(gst_transporter_id_field);
    },
});
