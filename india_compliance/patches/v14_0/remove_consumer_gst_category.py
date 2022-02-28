import frappe

def execute():
	if not frappe.db.exists("Company", {'country': 'India'}):
		return

	for doctype in ('Customer', 'Address', 'Supplier'):
		if frappe.db.has_column(doctype, 'gst_category'):
			frappe.db.set_value(doctype, {'gst_category': 'Consumer'}, 'gst_category', 			'Unregistered')
	
			# Remove Consumer option from Custom Field gst_category
			custom_field = frappe.db.get_value("Custom Field", {
				'dt':doctype,
				'fieldname':'gst_category',
				'fieldtype': 'Select'
				},['name','options'], as_dict=True)

			options = custom_field.options.split('\n')
			if "Consumer" in options:
				options.remove("Consumer")
				options_string = "\n".join(option for option in options)
				frappe.db.set_value("Custom Field", custom_field.name, 'options', options_string)


			