// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

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
