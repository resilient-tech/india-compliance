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
	attach_e_waybill_print: function(frm) {
		if(!frm.doc.attach_e_waybill_print || frm.doc.get_data_for_print) return;
		frm.set_value("get_data_for_print", 1);
	},
	after_save(frm) {
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
