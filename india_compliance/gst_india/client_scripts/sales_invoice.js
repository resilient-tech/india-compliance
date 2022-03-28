{% include "india_compliance/gst_india/client_scripts/taxes.js" %}
{% include "india_compliance/gst_india/client_scripts/einvoice.js" %}
{% include "india_compliance/gst_india/client_scripts/invoice.js" %}

const DOCTYPE = "Sales Invoice";

setup_auto_gst_taxation(DOCTYPE);
fetch_and_highlight_gst_category(DOCTYPE);
setup_einvoice_actions(DOCTYPE);
update_export_type(DOCTYPE);
e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
	setup(frm) {
		frm.set_query('transporter', {
			filters: {
				'is_transporter': 1
			}
		});

		frm.set_query('driver', (doc) => {
			return {
				filters: {
					'transporter': doc.transporter
				}
			};
		});
	},

	async refresh (frm) {
		let settings = frappe.boot.gst_settings
		if (frm.doc.ewaybill && frm.doc.ewaybill.length == 12 && settings.enable_api) {
			frm.set_df_property('ewaybill', 'allow_on_submit', 0);
		}
		if(frm.doc.docstatus != 1 || frm.is_dirty() || frm.doc.ewaybill || !settings.enable_e_waybill || !is_e_waybill_applicable(frm, settings.e_waybill_criteria)) return;
		// ewaybill is applicable and not created or updated.
		frm.dashboard.add_comment("e-Waybill is applicable for this invoice and not yet generated or updated.", "yellow");

		if (settings.enable_api) return;
		frm.add_custom_button('e-Waybill JSON', () => {
			open_url_post(frappe.request.url, {
				cmd: "india_compliance.gst_india.utils.e_waybill.download_e_waybill_json",
				doctype: frm.doctype,
				docnames: frm.doc.name,
			});
		}, __("Create"));
	},

	on_submit(frm) {
		let settings = frappe.boot.gst_settings
		if (frm.doc.ewaybill || !settings.enable_api || !settings.generate_e_waybill_on_submit || !is_e_waybill_applicable(frm, settings.e_waybill_criteria)) return;
		frappe.call({
			method: "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_if_possible",
			args: {
				doctype: frm.doc.doctype,
				docname: frm.doc.name
			},
			callback: () => frm.reload_doc()
		})
	}

});
