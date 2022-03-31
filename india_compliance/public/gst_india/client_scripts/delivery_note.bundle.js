import { setup_auto_gst_taxation, fetch_gst_category } from "./taxes";

const DOCTYPE = "Delivery Note";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });
    },
    refresh(frm) {
        if (frm.doc.docstatus == 1 && !frm.is_dirty() && !frm.doc.ewaybill) {
            frm.add_custom_button(
                "e-Waybill JSON",
                () => {
                    frappe.call({
                        method: "india_compliance.gst_india.utils.e_waybill.generate_ewb_json",
                        args: {
                            dt: frm.doc.doctype,
                            dn: [frm.doc.name],
                        },
                        callback: function (r) {
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
