import frappe


def get_itemised_tax_breakup_header(item_doctype, tax_accounts):
	hsn_wise_in_gst_settings = frappe.db.get_single_value('GST Settings','hsn_wise_tax_breakup')
	if frappe.get_meta(item_doctype).has_field('gst_hsn_code') and hsn_wise_in_gst_settings:
		return [_("HSN/SAC"), _("Taxable Amount")] + tax_accounts
	else:
		return [_("Item"), _("Taxable Amount")] + tax_accounts
