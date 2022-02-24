{% include "india_compliance/gst_india/client_script/taxes.js" %}

erpnext.setup_auto_gst_taxation('Delivery Note');

frappe.ui.form.on('Delivery Note', {
	refresh: function(frm) {
		if(frm.doc.docstatus == 1 && !frm.is_dirty() && !frm.doc.ewaybill) {
			frm.add_custom_button('E-Way Bill JSON', () => {
				frappe.call({
					method: 'india_compliance.gst_india.utils.e_waybill.generate_ewb_json',
					args: {
						'dt': frm.doc.doctype,
						'dn': [frm.doc.name]
					},
					callback: function(r) {
						if (r.message) {
							const args = {
								cmd: 'india_compliance.gst_india.utils.e_waybill.download_ewb_json',
								data: r.message,
								docname: frm.doc.name
							};
							open_url_post(frappe.request.url, args);
						}
					}
				});
			}, __("Create"));
		}
	}
})
