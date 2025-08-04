import frappe


def execute():
    legacy_reports = [
        "GSTR-1",
        "GST Sales Register Beta",
        "GST Purchase Register Beta",
        "GST Itemised Sales Register",
        "GST Itemised Purchase Register",
    ]

    for report_name in legacy_reports:
        try:
            frappe.delete_doc(
                "Report",
                report_name,
                force=True,
                ignore_permissions=True,
                delete_permanently=True,
            )

        except Exception as e:
            print(f"Error removing report {report_name}: {str(e)}")
