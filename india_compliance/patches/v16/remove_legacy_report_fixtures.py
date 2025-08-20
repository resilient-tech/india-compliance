import frappe


def execute():
    legacy_reports = [
        "GSTR-1",
        "GST Sales Register Beta",
        "GST Purchase Register Beta",
        "GST Itemised Sales Register",
        "GST Itemised Purchase Register",
    ]

    try:
        reports = frappe.get_all(
            "Report",
            filters={"reference_report": ("in", legacy_reports)},
            fields="name",
            pluck="name",
        )

        frappe.delete_doc(
            "Report",
            legacy_reports + reports,
            force=True,
            ignore_permissions=True,
            delete_permanently=True,
        )

    except Exception:
        frappe.log_error(title="remove_legacy_report_fixtures failed")
