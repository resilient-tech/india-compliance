import frappe


def execute():
    gst_settings = frappe.get_doc("GST Settings")

    company_account_list = []
    
    if frappe.db.exists("GST Account", {'is_output_account':1}):
        row_exists = False
        
        for row in gst_settings.gst_accounts:
            gst_accounts = (row.cgst_account.lower(), row.sgst_account.lower(), row.igst_account.lower())

            if not row.is_reverse_charge_account:
                if "output" in str(gst_accounts):
                    row.is_output_account = True

                if "input" in str(gst_accounts):
                    row.is_input_account = True
                
                for field in ['is_input_account', 'is_output_account']:
                    if row.get(field):
                        company_account_list.append({
                            'company': row.company, 
                            field: row.get(field)
                        })

                    dict_to_check = {'company': row.company, field: row.get(field)}

                    if company_account_list.count(dict_to_check) > 1:
                        if field == 'is_input_account':
                            row.is_input_account = False
                        elif field == 'is_output_account':
                            row.is_output_account = False
            row_exists = True
                            
        gst_settings.save()
        frappe.db.commit()
        
        if not row_exists:
            return
