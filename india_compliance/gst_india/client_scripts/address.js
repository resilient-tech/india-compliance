{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Address";

validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
show_overseas_disabled_warning(DOCTYPE);
set_gstin_options_and_status(DOCTYPE);
set_gst_category(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    country(frm) {
        india_compliance.set_state_options(frm);

        if (!frm.doc.country) return;

        // Assume default country to be India for now
        // Automatically set GST Category as Overseas if country is not India
        if (frm.doc.country != "India")
            frm.set_value("gst_category", "Overseas");
        else
            frm.trigger("gstin");
    },
    async refresh(frm) {
        india_compliance.set_state_options(frm);

        // set default values for GST fields
        if (!frm.is_new() || !frm.doc.links || frm.doc.gstin) return;

        const row = frm.doc.links[0];
        if (!frappe.boot.gst_party_types.includes(row.link_doctype)) return;

        // Try to get clean doc from locals
        let doc = frappe.get_doc(row.link_doctype, row.link_name);

        // Fallback to DB
        if (!doc || doc.__unsaved || doc.__islocal) {
            const { message } = await frappe.db.get_value(
                row.link_doctype,
                row.link_name,
                ["gstin", "gst_category"]
            );

            if (message) {
                doc = message;
            } else {
                return;
            }
        }

        frm.set_value("gstin", doc.gstin || "");
        frm.set_value("gst_category", doc.gst_category || "");
    },
});
