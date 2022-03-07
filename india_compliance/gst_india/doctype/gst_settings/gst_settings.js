// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('GST Settings', {
	refresh: function(frm) {
		frm.add_custom_button('Send GST Update Reminder', () => {
			return new Promise((resolve) => {
				return frappe.call({
					method: 'india_compliance.gst_india.doctype.gst_settings.gst_settings.send_reminder'
				}).always(() => { resolve(); });
			});
		});

		$(frm.fields_dict.gst_summary.wrapper).empty().html(
			`<table class="table table-bordered">
				<tbody>
				<tr>
				<td>Total Addresses</td><td>${frm.doc.__onload.data.total_addresses}</td>
				</tr><tr>
				<td>Total Addresses with GST</td><td>${frm.doc.__onload.data.total_addresses_with_gstin}</td>
				</tr>
			</tbody></table>`
		);
	},

	setup: function(frm) {
		$.each(["cgst_account", "sgst_account", "igst_account", "cess_account"], function(i, field) {
			frm.events.filter_accounts(frm, field);
		});
		
		frm.set_query('company', "gst_accounts", function() {
			return {
				filters: {
					country: "India"
				}
			}
		});
	},

	filter_accounts: function(frm, account_field) {
		frm.set_query(account_field, "gst_accounts", function(doc, cdt, cdn) {
			var row = locals[cdt][cdn];
			return {
				filters: {
					company: row.company,
					account_type: "Tax",
					is_group: 0
				}
			};
		});
	},

});
