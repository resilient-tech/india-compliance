{% include "india_compliance/gst_india/client_scripts/taxes.js" %}
{% include "india_compliance/gst_india/client_scripts/einvoice.js" %}

const DOCTYPE = "Sales Invoice";

setup_auto_gst_taxation(DOCTYPE);
highlight_gst_category(DOCTYPE);
setup_einvoice_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
	setup: function(frm) {
		frm.set_query('transporter', function() {
			return {
				filters: {
					'is_transporter': 1
				}
			};
		});

		frm.set_query('driver', function(doc) {
			return {
				filters: {
					'transporter': doc.transporter
				}
			};
		});
	},

	refresh: async function(frm) {
		if(frm.doc.docstatus != 1 || frm.is_dirty()	|| frm.doc.ewaybill) return;

		let {message} = await frappe.db.get_value("GST Settings", "GST Settings", ("enable_e_waybill", "api_secret", "e_waybill_criteria"));
		if (message.enable_e_waybill != 1 || !is_e_waybill_applicable(frm, message.e_waybill_criteria)) return;

		frm.dashboard.add_comment("e-Waybill is applicable for this invoice and not yet generated or updated.", "yellow");

		if (message.api_secret) return;

		frm.add_custom_button('e-Waybill JSON', () => {
			open_url_post(frappe.request.url, {
				cmd: "india_compliance.gst_india.utils.e_waybill.download_e_waybill_json",
				doctype: frm.doctype,
				docnames: frm.doc.name,
			});
		}, __("Create"));
	}

});


function is_e_waybill_applicable(frm, e_waybill_criteria) {
	if (frm.doc.base_grand_total < e_waybill_criteria) return false;
	for (let item of frm.doc.items) {
		if (!item.gst_hsn_code.startsWith("99")) return true;
	}
	return false;
}