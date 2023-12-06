frappe.ui.form.on("Payment Entry", {
	company: function (frm) {
		frappe.call({
			method: "frappe.contacts.doctype.address.address.get_default_address",
			args: {
				doctype: "Company",
				name: frm.doc.company,
			},
			callback: function (r) {
				frm.set_value("company_address", r.message);
			},
		});
	},

	party: function (frm) {
		update_gst_details(
			frm,
			"india_compliance.gst_india.overrides.payment_entry.update_party_details"
		);
	},

	customer_address(frm) {
		update_gst_details(frm);
	},
});

async function update_gst_details(frm, method) {
	if (
		frm.doc.party_type != "Customer" ||
		!frm.doc.party ||
		frm.__updating_gst_details
	)
		return;

	// wait for GSTINs to get fetched
	await frappe.after_ajax();

	args = {
		doctype: frm.doc.doctype,
		party_details: {
			customer: frm.doc.party,
			customer_address: frm.doc.customer_address,
			billing_address_gstin: frm.doc.billing_address_gstin,
			gst_category: frm.doc.gst_category,
			company_gstin: frm.doc.company_gstin,
		},
		company: frm.doc.company,
	};

	india_compliance.fetch_and_update_gst_details(frm, args, method);
}
