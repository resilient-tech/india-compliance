{% include "india_compliance/gst_india/client_scripts/taxes.js" %}

const DOCTYPE = "Delivery Note";

setup_auto_gst_taxation(DOCTYPE);
highlight_gst_category(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
	refresh: function(frm) {
		if(frm.doc.docstatus != 1 || frm.is_dirty() || frm.doc.ewaybill) return;

		let {message} = await frappe.db.get_value("GST Settings", "GST Settings", ("enable_e_waybill", "api_secret"));
		if (message.enable_e_waybill != 1) return; // currently support for e-waybill using API from delivery note is not planned.

		frm.add_custom_button('e-Waybill JSON', () => {
			open_url_post(frappe.request.url, {
				cmd: "india_compliance.gst_india.utils.e_waybill.download_e_waybill_json",
				doctype: frm.doctype,
				docnames: frm.doc.name,
			});
		}, __("Create"));
	}
})
