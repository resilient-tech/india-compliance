import frappe

def execute():
	company = frappe.get_all("Company", {'country': 'India'})

	if not company:
		return

	for doctype in ['Customer', 'Address', 'Contact', 'Supplier']:
		has_column = frappe.db.has_column(doctype, 'gst_category')
		if has_column:
			all_consumer_category = frappe.get_all(doctype, {'gst_category': 'Consumer'})
			for data in all_consumer_category:
				doc = frappe.get_doc(doctype, data.name)
				doc.db_set('gst_category', 'Unregistered', commit=True)

	
			# Remove Consumer option from Custom Field gst_category
			doc = frappe.get_doc("Custom Field", {
			'fieldname': 'gst_category', 
			'dt': doctype
			})
			if doc.fieldtype=='Select' and doc.options:
				options = doc.options.split('\n')
				if "Consumer" in options:
					options.remove("Consumer")
					options_string = "\n".join(d for d in options)
					doc.db_set("options", options_string, commit=True)
				else:
					frappe.throw(f"Consumer option not available in {doc.fieldname}")


			