frappe.ui.form.on('Item', {
	onload: function(frm) {
		if (!gst_settings.validate_hsn_code) return;
		frm.set_query('gst_hsn_code', function() {
			const wildcard = '_'.repeat(gst_settings.min_hsn_digits) + '%';
			return {
				filters: {
					'name': ['like', wildcard]
				}
			};
		});
	},

	gst_hsn_code: function(frm) {
		if ((!frm.doc.taxes || !frm.doc.taxes.length) && frm.doc.gst_hsn_code) {
			frappe.db.get_doc("GST HSN Code", frm.doc.gst_hsn_code).then(hsn_doc => {
				$.each(hsn_doc.taxes || [], function(_, tax) {
					let a = frappe.model.add_child(frm.doc, 'Item Tax', 'taxes');
					a.item_tax_template = tax.item_tax_template;
					a.tax_category = tax.tax_category;
					a.valid_from = tax.valid_from;
					frm.refresh_field('taxes');
				});
			});
		}
	},
});
