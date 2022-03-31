const erpnext_onload = frappe.listview_settings['Sales Invoice'].onload;
frappe.listview_settings['Sales Invoice'].onload = function (list_view) {

	// Provision in case onload event is added to ERPNext in future
	if (erpnext_onload) {
		erpnext_onload(list_view);
	}

	const action = () => {
		const selected_docs = list_view.get_checked_items();
		const docnames = list_view.get_checked_items(true);

		for (let doc of selected_docs) {
			if (doc.docstatus !== 1) {
				frappe.throw(__("e-Waybill JSON can only be generated from a submitted document"));
			}
		}

		frappe.call({
			method: 'india_compliance.gst_india.utils.e_waybill.generate_ewb_json',
			args: {
				'dt': list_view.doctype,
				'dn': docnames
			},
			callback: function(r) {
				if (r.message) {
					const args = {
						cmd: 'india_compliance.gst_india.utils.e_waybill.download_ewb_json',
						data: r.message,
						docname: docnames
					};
					open_url_post(frappe.request.url, args);
				}
			}
		});
	};

	list_view.page.add_actions_menu_item(__('Generate e-Waybill JSON'), action, false);

	const generate_irns = () => {
		const docnames = list_view.get_checked_items(true);
		if (docnames && docnames.length) {
			frappe.call({
				method: 'india_compliance.gst_india.utils.e_invoice.generate_einvoices',
				args: { docnames },
				freeze: true,
				freeze_message: __('Generating e-Invoices...')
			});
		} else {
			frappe.msgprint({
				message: __('Please select at least one sales invoice to generate IRN'),
				title: __('No Invoice Selected'),
				indicator: 'red'
			});
		}
	};

	const cancel_irns = () => {
		const docnames = list_view.get_checked_items(true);

		const fields = [
			{
				"label": "Reason",
				"fieldname": "reason",
				"fieldtype": "Select",
				"reqd": 1,
				"default": "1-Duplicate",
				"options": ["1-Duplicate", "2-Data Entry Error", "3-Order Cancelled", "4-Other"]
			},
			{
				"label": "Remark",
				"fieldname": "remark",
				"fieldtype": "Data",
				"reqd": 1
			}
		];

		const d = new frappe.ui.Dialog({
			title: __("Cancel IRN"),
			fields: fields,
			primary_action: function() {
				const data = d.get_values();
				frappe.call({
					method: 'india_compliance.gst_india.utils.e_invoice.cancel_irns',
					args: {
						doctype: list_view.doctype,
						docnames,
						reason: data.reason.split('-')[0],
						remark: data.remark
					},
					freeze: true,
					freeze_message: __('Cancelling e-Invoices...'),
				});
				d.hide();
			},
			primary_action_label: __('Submit')
		});
		d.show();
	};

	let einvoicing_enabled = false;
	frappe.db.get_single_value("E Invoice Settings", "enable").then(enabled => {
		einvoicing_enabled = enabled;
	});

	list_view.$result.on("change", "input[type=checkbox]", () => {
		if (einvoicing_enabled) {
			const docnames = list_view.get_checked_items(true);
			// show/hide e-invoicing actions when no sales invoices are checked
			if (docnames && docnames.length) {
				// prevent adding actions twice if e-invoicing action group already exists
				if (list_view.page.get_inner_group_button(__('E-Invoicing')).length == 0) {
					list_view.page.add_inner_button(__('Generate IRNs'), generate_irns, __('E-Invoicing'));
					list_view.page.add_inner_button(__('Cancel IRNs'), cancel_irns, __('E-Invoicing'));
				}
			} else {
				list_view.page.remove_inner_button(__('Generate IRNs'), __('E-Invoicing'));
				list_view.page.remove_inner_button(__('Cancel IRNs'), __('E-Invoicing'));
			}
		}
	});

	frappe.realtime.on("bulk_einvoice_generation_complete", (data) => {
		const { failures, user, invoices } = data;

		if (invoices.length != failures.length) {
			frappe.msgprint({
				message: __('{0} e-Invoices generated successfully', [invoices.length]),
				title: __('Bulk e-Invoice Generation Complete'),
				indicator: 'orange'
			});
		}

		if (failures && failures.length && user == frappe.session.user) {
			let message = `
				Failed to generate IRNs for following ${failures.length} sales invoices:
				<ul style="padding-left: 20px; padding-top: 5px;">
					${failures.map(d => `<li>${d.docname}</li>`).join('')}
				</ul>
			`;
			frappe.msgprint({
				message: message,
				title: __('Bulk e-Invoice Generation Complete'),
				indicator: 'orange'
			});
		}
	});

	frappe.realtime.on("bulk_einvoice_cancellation_complete", (data) => {
		const { failures, user, invoices } = data;

		if (invoices.length != failures.length) {
			frappe.msgprint({
				message: __('{0} e-Invoices cancelled successfully', [invoices.length]),
				title: __('Bulk e-Invoice Cancellation Complete'),
				indicator: 'orange'
			});
		}

		if (failures && failures.length && user == frappe.session.user) {
			let message = `
				Failed to cancel IRNs for following ${failures.length} sales invoices:
				<ul style="padding-left: 20px; padding-top: 5px;">
					${failures.map(d => `<li>${d.docname}</li>`).join('')}
				</ul>
			`;
			frappe.msgprint({
				message: message,
				title: __('Bulk e-Invoice Cancellation Complete'),
				indicator: 'orange'
			});
		}
	});
};
