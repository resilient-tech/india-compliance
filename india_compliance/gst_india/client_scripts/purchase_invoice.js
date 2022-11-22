const DOCTYPE = "Purchase Invoice";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
	after_save(frm) {
		if (
			frm.doc.docstatus ||
			frm.doc.supplier_address ||
			!(gst_settings.enable_e_waybill && gst_settings.enable_e_waybill_from_pi)
		)
			return;

		frappe.show_alert({
			message: __("Supplier Address is required to create e-Waybill"),
			indicator: "yellow",
		}, 10);
	},
});