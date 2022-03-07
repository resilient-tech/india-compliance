import frappe


def execute():    
    if frappe.db.exists("GST Account", {'gst_account_type':'Output'}) or frappe.db.exists("GST Account", {'gst_account_type':'Input'}):
        gst_settings = frappe.get_doc("GST Settings")

        company_account_list = []
        row_exists = False
        
        for row in gst_settings.gst_accounts:
            gst_accounts = (row.cgst_account.lower(), row.sgst_account.lower(), row.igst_account.lower())

            if not row.is_reverse_charge_account:
                if "output" in str(gst_accounts):
                    row.gst_account_type = 'Output'

                if "input" in str(gst_accounts):
                    row.gst_account_type = 'Input'

                if row.gst_account_type:
                    company_account_list.append({
                        'company': row.company, 
                        'gst_account_type': row.gst_account_type
                    })

                # If duplicate value found set gst account type to None
                for data in company_account_list:
                    print(company_account_list.count(data))
                    if company_account_list.count(data) > 1:
                        row.gst_account_type = ''
            else:
                row.gst_account_type = 'Reverse Charge'

            row_exists = True

        gst_settings.save()
        
        if not row_exists:
            return


