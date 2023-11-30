const WARNING_ICON = `
	<span class='warning-icon link-btn mb-auto mt-auto' style='display: block; z-index: 1; top: 5px; width: 24px; height: 24px'>
		<svg xmlns="http://www.w3.org/2000/svg" fill-rule="evenodd" stroke-linejoin="round" stroke-miterlimit="2" clip-rule="evenodd" viewBox="0 0 500 500" id="warning">
			<path fill="#ffeb00" d="M200.962,136.327C210.278,117.789 229.252,106.089 250,106.089C270.748,106.089 289.722,117.789 299.038,136.327C335.995,209.866 386.041,309.448 420.583,378.179C429.133,395.193 428.254,415.422 418.26,431.629C408.266,447.837 390.586,457.706 371.545,457.706L128.455,457.706C109.414,457.706 91.734,447.837 81.74,431.629C71.746,415.422 70.867,395.193 79.417,378.179C113.959,309.448 164.005,209.866 200.962,136.327Z" transform="translate(-29.627 -65.304) scale(1.11851)"></path><path d="M177.28,78.198L41.332,348.711C28.653,373.94 29.957,403.939 44.777,427.973C59.597,452.007 85.815,466.643 114.052,466.643L385.948,466.643C414.185,466.643 440.403,452.007 455.223,427.973C470.043,403.939 471.347,373.94 458.668,348.711C420.033,271.835 364.057,160.451 322.72,78.198C308.904,50.707 280.767,33.357 250,33.357C219.233,33.357 191.096,50.707 177.28,78.198ZM213.021,96.159C220.046,82.18 234.354,73.357 250,73.357C265.646,73.357 279.954,82.18 286.979,96.159C328.316,178.413 384.293,289.796 422.927,366.672C429.375,379.502 428.712,394.757 421.176,406.978C413.64,419.2 400.307,426.643 385.948,426.643L114.052,426.643C99.693,426.643 86.36,419.2 78.824,406.978C71.288,394.757 70.625,379.502 77.073,366.672L213.021,96.159ZM270,371.595L270,369.717C270,358.679 261.038,349.717 250,349.717C238.962,349.717 230,358.679 230,369.717L230,371.595C230,382.633 238.962,391.595 250,391.595C261.038,391.595 270,382.633 270,371.595ZM230,150.561L230,312.904C230,323.943 238.962,332.904 250,332.904C261.038,332.904 270,323.943 270,312.904L270,150.561C270,139.523 261.038,130.561 250,130.561C238.962,130.561 230,139.523 230,150.561Z">
			</path>
		</svg>
	</span>
`;


frappe.ui.form.on("Payment Entry", {

	refresh: fetch_reconciliation_status,

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

frappe.ui.form.on("Payment Entry Reference", {
	reference_name(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);

		if (row.reference_doctype !== "Purchase Invoice") return;

		frappe.db.get_value(row.reference_doctype, row.reference_name, 'reconciliation_status')
			.then(response => {
				if (!response.message) return;

				let reconciliation_status_list = [{
					name: row.reference_name,
					reconciliation_status: response.message.reconciliation_status
				}]

				add_warning_indicator(frm, reconciliation_status_list);
			});
	},
});

function fetch_reconciliation_status(frm) {

	const invoice_list = frm.doc.references
		.filter((row) => row.reference_doctype === "Purchase Invoice")
		.map((row) => row.reference_name);

	if (invoice_list.length === 0) return;


	frappe.db.get_list('Purchase Invoice', {
		fields: ['name', 'reconciliation_status'],
		filters: {
			name: ["in", invoice_list]
		}
	}).then(reconciliation_status_list => {
		if (!reconciliation_status_list) return;
		add_warning_indicator(frm, reconciliation_status_list);
	});

}

function add_warning_indicator(frm, reconciliation_status_list) {

	for (const item of reconciliation_status_list) {
		if (item.reconciliation_status !== "Unreconciled") continue;

		const rows = frm.fields_dict.references.grid.grid_rows
			.filter((r) => r.doc.reference_name === item.name);

		for (const row of rows) {
			const targetDiv = row.columns.reference_name;
			const isWarningIconAlreadyPresent = $(targetDiv).find(".warning-icon").length > 0;

			if (isWarningIconAlreadyPresent) break;

			$(WARNING_ICON).appendTo(targetDiv);

			$('.warning-icon').hover(
				function () {
					$(this).attr('title', '2A/2B Status: Unreconciled');
				},
				function () {
					$(this).removeAttr('title');
				}
			);
		}
	}
}

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
