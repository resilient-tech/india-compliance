import frappe


def execute():
    frappe.db.sql(
        """UPDATE `tabSales Invoice` SET gst_category = 'Unregistered'
        WHERE gst_category = 'Registered Regular'
        AND IFNULL(customer_gstin, '') = ''
        AND IFNULL(billing_address_gstin,'') = ''
    """
    )

    frappe.db.sql(
        """UPDATE `tabPurchase Invoice` SET gst_category = 'Unregistered'
        WHERE gst_category = 'Registered Regular'
        AND IFNULL(supplier_gstin, '') = ''
    """
    )
