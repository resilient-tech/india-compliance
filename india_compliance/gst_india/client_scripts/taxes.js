frappe.provide("hsn_valid");

function setup_auto_gst_taxation (doctype) {
	frappe.ui.form.on(doctype, {
		company_address: function(frm) {
			frm.trigger('get_tax_template');
		},
		shipping_address: function(frm) {
			frm.trigger('get_tax_template');
		},
		supplier_address: function(frm) {
			frm.trigger('get_tax_template');
		},
		tax_category: function(frm) {
			frm.trigger('get_tax_template');
		},
		customer_address: function(frm) {
			frm.trigger('get_tax_template');
		},
		get_tax_template: function(frm) {
			if (!frm.doc.company) return;

			let party_details = {
				'shipping_address': frm.doc.shipping_address || '',
				'shipping_address_name': frm.doc.shipping_address_name || '',
				'customer_address': frm.doc.customer_address || '',
				'supplier_address': frm.doc.supplier_address,
				'customer': frm.doc.customer,
				'supplier': frm.doc.supplier,
				'supplier_gstin': frm.doc.supplier_gstin,
				'company_gstin': frm.doc.company_gstin,
				'tax_category': frm.doc.tax_category
			};

			frappe.call({
				method: 'india_compliance.gst_india.overrides.transaction.get_regional_address_details',
				args: {
					party_details: JSON.stringify(party_details),
					doctype: frm.doc.doctype,
					company: frm.doc.company
				},
				debounce: 2000,
				callback: function(r) {
					if(r.message) {
						frm.set_value('taxes_and_charges', r.message.taxes_and_charges);
						frm.set_value('taxes', r.message.taxes);
						frm.set_value('place_of_supply', r.message.place_of_supply);
					}
				}
			});
		}
	});
}

function validate_hsn_code(doctype){
	frappe.ui.form.on(doctype, {
		after_save: function(frm) {
			call_validate_hsn_code(frm, 'validate_hsn_code');
		},
		before_submit: function(frm) {
			call_validate_hsn_code(frm, 'validate_hsn_code_before_submit');
		}
	});

	frappe.ui.form.on(doctype + " Item", {
		item_code: function(frm, cdt, cdn) {
			hsn_valid[frm.docname] = false;
		},
		gst_hsn_code: function(frm, cdt, cdn) {
			hsn_valid[frm.docname] = false;
		}
	});
}

function call_validate_hsn_code (frm, func){
	if (hsn_valid[frm.docname]) return;
	frappe.call({
		method: 'india_compliance.gst_india.doctype.gst_settings.gst_settings.' + func,
		args: {
			items: frm.doc.items,
		},
		callback: function(r){
			if (r) {
				hsn_valid[frm.docname] = r.message;
			}
		}
	})
}

function highlight_gst_category(doctype, party_type) {
	frappe.ui.form.on(doctype, {
		refresh: function(frm) {
			_highlight_gst_category(frm, party_type);
		},
		gst_category: function(frm) {
			_highlight_gst_category(frm, party_type);
		}
	});
}

function _highlight_gst_category(frm, party_type) {
	if (!frm.doc[party_type] || !frm.doc.gst_category) return;
	frm.fields_dict.customer.set_description('<i>' + frm.doc.gst_category+ '</i>');
}