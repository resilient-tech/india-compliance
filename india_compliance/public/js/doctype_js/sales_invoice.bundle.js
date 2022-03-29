import { setup_auto_gst_taxation, fetch_gst_category } from "./taxes";
import { setup_einvoice_actions } from "./einvoice";
import { update_export_type } from "./invoice";

const DOCTYPE = "Sales Invoice";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
setup_einvoice_actions(DOCTYPE);
update_export_type(DOCTYPE);

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

    refresh(frm) {
        if (
            frm.doc.docstatus == 1 &&
            !frm.is_dirty() &&
            !frm.doc.is_return &&
            !frm.doc.ewaybill
        ) {
            frm.add_custom_button(
                "e-Waybill JSON",
                () => {
                    frappe.call({
                        method: "india_compliance.gst_india.utils.e_waybill.generate_ewb_json",
                        args: {
                            dt: frm.doc.doctype,
                            dn: [frm.doc.name],
                        },
                        callback(r) {
                            if (r.message) {
                                const args = {
                                    cmd: "india_compliance.gst_india.utils.e_waybill.download_ewb_json",
                                    data: r.message,
                                    docname: frm.doc.name,
                                };
                                open_url_post(frappe.request.url, args);
                            }
                        },
                    });
                },
                __("Create")
            );
        }
    },
});
