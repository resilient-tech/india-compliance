// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

{% include "india_compliance/gst_india/client_scripts/gstin_query.js" %}

frappe.ui.form.on('GST Settings', {
	setup: function(frm) {
		$.each(["cgst_account", "sgst_account", "igst_account", "cess_account"], function(i, field) {
			frm.events.filter_accounts(frm, field);
		});

		const company_query = {
			filters: {
				country: "India",
			}
		}

		frm.set_query('company', "gst_accounts", company_query);
		frm.set_query('company', "credentials", company_query);
		frm.set_query('gstin', "credentials", function(doc, cdt, cdn) {
			const row = frappe.get_doc(cdt, cdn);
			return get_gstin_query(row.company);
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

	enable_reverse_charge: function (frm) {
		if (frm.doc.enable_reverse_charge) {
			frappe.confirm('Do you wish to enable Reverse Charge in Sales Invoice?',
				() => {
					return;
				}, () => {
					frm.set_value('enable_reverse_charge', false);
				})
		}
	}

});
