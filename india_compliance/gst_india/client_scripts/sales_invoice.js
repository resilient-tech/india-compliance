{% include "india_compliance/gst_india/client_scripts/taxes.js" %}
{% include "india_compliance/gst_india/client_scripts/invoice.js" %}

const DOCTYPE = "Sales Invoice";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
update_export_type(DOCTYPE);
setup_e_waybill_actions(DOCTYPE);

const gst_settings = frappe.boot.gst_settings;

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
		if (gst_settings.enable_api && frm.doc.ewaybill && frm.doc.ewaybill.length == 12) {
			frm.set_df_property('ewaybill', 'allow_on_submit', 0);
		}

		if(
			frm.doc.docstatus != 1
			|| frm.is_dirty()
			|| frm.doc.ewaybill
			|| !gst_settings.enable_e_waybill
			|| !is_e_waybill_applicable(frm)
		) return;

		if (!frm.doc.is_return) {
			// ewaybill is applicable and not created or updated.
			frm.dashboard.add_comment(
				"e-Waybill is applicable for this invoice and not yet generated or updated.",
				"yellow"
			);
		}

		if (gst_settings.enable_api) return;

		frm.add_custom_button('e-Waybill JSON', async () => {
			const ewb_data = await frappe.xcall(
				"india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
				{doctype: frm.doctype, docnames: frm.doc.name}
			);

			trigger_file_download(ewb_data, get_e_waybill_file_name(frm.doc.name));
		}, __("Create"));
	},

	on_submit(frm) {
		if (
			frm.doc.ewaybill
			|| frm.doc.is_return
			|| !gst_settings.enable_api
			|| !gst_settings.auto_generate_e_waybill
			|| ( gst_settings.enable_e_invoice && gst_settings.auto_generate_e_invoice)
			|| !is_e_waybill_applicable(frm)
		) return;

		frappe.call({
			method: "india_compliance.gst_india.utils.e_waybill.auto_generate_e_waybill",
			args: {
				doctype: frm.doc.doctype,
				docname: frm.doc.name
			},
			callback: () => frm.reload_doc()
		})
	}
});
