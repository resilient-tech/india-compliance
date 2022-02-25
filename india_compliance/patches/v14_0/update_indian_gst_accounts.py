import frappe


def execute():
    gst_settings_doc = frappe.get_doc("GST Settings")
    
    for row in gst_settings_doc.gst_accounts:
        gst_accounts = (row.cgst_account and row.sgst_account and row.igst_account)

        if not row.is_reverse_charge_account:
            if "Output" in gst_accounts:
                row.is_output_account = True

            if "Input" in gst_accounts:
                row.is_input_account = True

    gst_settings_doc.save()
    frappe.db.commit()