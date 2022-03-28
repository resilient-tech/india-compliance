{% include "india_compliance/gst_india/client_scripts/taxes.js" %}

const DOCTYPE = "Delivery Note";

setup_auto_gst_taxation(DOCTYPE);
fetch_and_highlight_gst_category(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
	setup(frm) {
		frm.set_query('transporter', {
			filters: {
				'is_transporter': 1
			}
		});
	},
	refresh(frm) {
		if(frm.doc.docstatus != 1 || frm.is_dirty() || frm.doc.ewaybill || !frappe.boot.gst_settings.enable_e_waybill) return;

		frm.add_custom_button('e-Waybill JSON', () => {
			open_url_post(frappe.request.url, {
				cmd: "india_compliance.gst_india.utils.e_waybill.download_e_waybill_json",
				doctype: frm.doctype,
				docnames: frm.doc.name,
			});
		}, __("Create"));
	},
})
