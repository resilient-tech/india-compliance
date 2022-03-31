// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

{% include "india_compliance/gst_india/client_scripts/gstin_query.js" %}

frappe.ui.form.on('GST Settings', {
	setup(frm) {
		(["cgst_account", "sgst_account", "igst_account", "cess_account"]).forEach(
			field => filter_accounts(frm, field)
		);

		const company_query = {
			filters: {
				country: "India",
			}
		}

		frm.set_query('company', "gst_accounts", company_query);
		frm.set_query('company', "credentials", company_query);
		frm.set_query('gstin', "credentials", (_, cdt, cdn) => {
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

	after_save(frm) {
		// sets latest values in frappe.boot for current user
		// other users will still need to refresh page
		frappe.boot.gst_settings = frm.doc;
	}
});

function filter_accounts(frm, account_field) {
	frm.set_query(account_field, "gst_accounts", (_, cdt, cdn) => {
		const row = frappe.get_doc(cdt, cdn);
		return {
			filters: {
				company: row.company,
				account_type: "Tax",
				is_group: 0
			}
		};
	});
}
