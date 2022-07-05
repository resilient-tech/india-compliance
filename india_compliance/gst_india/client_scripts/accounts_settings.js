frappe.ui.form.on("Accounts Settings", {
	onload: function (frm) {
		$(frm.get_field("determine_address_tax_category_from").$wrapper).before(`<div class="mb-3 text-small">${__("<b>Settings overriden by India Compliance App.</b>")}</div>`);
	}
});