import frappe


def execute():
    # Update Customer/Supplier Masters
    frappe.db.sql(
        """
        UPDATE `tabCustomer` set export_type = '' WHERE gst_category NOT IN ('SEZ', 'Overseas', 'Deemed Export')
    """
    )

    frappe.db.sql(
        """
        UPDATE `tabSupplier` set export_type = '' WHERE gst_category NOT IN ('SEZ', 'Overseas')
    """
    )
