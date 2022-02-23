import frappe


def delete_gst_settings_for_company(doc, method):
	if doc.country != 'India':
		return

	gst_settings = frappe.get_doc("GST Settings")
	records_to_delete = []

	for d in reversed(gst_settings.get('gst_accounts')):
		if d.company == doc.name:
			records_to_delete.append(d)

	for d in records_to_delete:
		gst_settings.remove(d)

	gst_settings.save()
